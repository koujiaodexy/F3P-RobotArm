"""Bounded illumination compensation for colour blocks, without motor IO.

Consumes the FPGA's blurred H/S plus raw value planes. A small neutral sample
updates a cached H/S table; HDMI pixels are not read back or rendered by Python.
The camera owner must retain its existing frame verification before publishing.
"""
import ctypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import math
import threading
import time

from .color_blocks import (COLORS, LABELS, BlockParameters, DEFAULT_BANDS,
                           validate_bands, saturation_floors, canonical_hsv, _hue_tables)
from .vision import dependencies


@dataclass(frozen=True)
class LightingCalibration:
    # Bright neutral reference measured alongside the user's calibrated blocks.
    # These ratios preserve existing camera-space hue calibration at the baseline.
    white_bgr: tuple = (172., 198., 204.)
    sample_step: int = 8
    minimum_samples: int = 32
    maximum_neutral_saturation: int = 110
    minimum_gain: float = .65
    maximum_gain: float = 1.55
    minimum_confidence: float = .46


def estimate_gains(hue, sat, value, calibration=LightingCalibration()):
    cv, np = dependencies()
    step = calibration.sample_step
    sample = np.stack((hue[::step, ::step], sat[::step, ::step], value[::step, ::step]), axis=-1)
    pixels = cv.cvtColor(sample, cv.COLOR_HSV2BGR)
    v = sample[:, :, 2]
    lib=native_ops()
    if lib is not None:
        stats=np.empty(6,np.float64)
        rc=lib.f3p_adaptive_white(pixels.ctypes.data,sample.ctypes.data,v.size,v.shape[1],calibration.maximum_neutral_saturation,stats.ctypes.data)
        if rc:raise ValueError('Invalid neutral sample')
        count=int(stats[0]);white=stats[1:4];coverage=tuple(map(float,stats[4:6]))
    else:
        cutoff = max(32., float(np.percentile(v, 80)))
        valid = ((v >= cutoff) & (v < 248) &
                 (sample[:, :, 1] <= calibration.maximum_neutral_saturation))
        count = int(np.count_nonzero(valid))
        ys,xs=np.nonzero(valid)
        coverage=((int(xs.max())-int(xs.min())+1)/v.shape[1],(int(ys.max())-int(ys.min())+1)/v.shape[0]) if count else (0.,0.)
    quality = {'neutral_samples': count, 'neutral_spread':list(coverage),'illumination_reference_valid': False}
    # A single pale block on a dark table must not become the white reference.
    if count < calibration.minimum_samples or coverage[0]<.55 or coverage[1]<.30:
        return (1., 1., 1.), quality
    if lib is None:white = np.median(pixels[valid], axis=0).astype(float)
    if float(white.min()) < 12.:
        return (1., 1., 1.), quality
    reference = np.asarray(calibration.white_bgr, dtype=float)
    gains = (reference / reference[1]) / (white / white[1])
    if not np.isfinite(gains).all() or gains.min() < calibration.minimum_gain or gains.max() > calibration.maximum_gain:
        return (1., 1., 1.), quality
    # Quantization avoids rebuilding a 46k-entry table for sensor-level jitter.
    gains = tuple(round(float(g), 2) for g in gains)
    quality.update(illumination_reference_valid=True, white_bgr=[round(float(v), 1) for v in white],
                   gains_bgr=list(gains))
    return gains, quality


# At capacity, both tables below retain 33.75 MiB of array payload in total
# (128 * 180 * 256 * (1 + 1 + 4)). The gain values and lookup math are unchanged;
# retaining more already-used gains prevents repeated rebuilds under jitter.
@lru_cache(maxsize=1)
def _correction_basis():
    """Gain-independent OpenCV conversion, retaining only 0.62 MiB of arrays."""
    cv, np = dependencies()
    h = np.repeat(np.arange(180, dtype=np.uint8)[:, None], 256, axis=1)
    s = np.repeat(np.arange(256, dtype=np.uint8)[None, :], 180, axis=0)
    hsv = np.stack((h.astype(np.float32) * 2, s.astype(np.float32) / 255,
                    np.ones(h.shape, np.float32)), axis=-1)
    return h, s, cv.cvtColor(hsv, cv.COLOR_HSV2BGR)


@lru_cache(maxsize=128)
def correction_table(gains):
    cv, np = dependencies()
    h, s, basis = _correction_basis()
    if gains == (1., 1., 1.):
        return h, s
    # Float conversion avoids clipping normalized colours when a gain exceeds 1.
    # Preserve the original float operations and conversion exactly; only the
    # identical HSV-to-BGR input work is shared between different gain values.
    bgr = basis.copy()
    bgr *= np.asarray(gains, np.float32) / max(gains)
    corrected = cv.cvtColor(bgr, cv.COLOR_BGR2HSV)
    return (np.mod(np.rint(corrected[:, :, 0] / 2), 180).astype(np.uint8),
            np.clip(np.rint(corrected[:, :, 1] * 255), 0, 255).astype(np.uint8))


@lru_cache(maxsize=128)
def classification_table(gains, bands_key, floors_key):
    cv, np = dependencies()
    h, s = correction_table(gains)
    lookup, _ = _hue_tables(bands_key)
    classes = cv.LUT(h, lookup)
    floors = np.asarray((255,) + floors_key, np.uint8)
    classes = np.where(s >= floors[classes], classes, 0).astype(np.uint32)
    return np.ascontiguousarray(h.astype(np.uint32) | (s.astype(np.uint32) << 8) | (classes << 16))


@lru_cache(maxsize=16)
def confidence_orders(key):
    _, np = dependencies()
    _, costs = _hue_tables(key)
    return [(np.ascontiguousarray(costs[i], dtype=np.float32), np.argsort(costs[i, :180], kind='stable').astype(np.uint8)) for i in range(4)]


def detect_features(hue, sat, value, parameters=None, bands=None, source_size=None,
                    calibration=LightingCalibration()):
    cv, np = dependencies()
    p = (parameters or BlockParameters()).validate()
    bands = validate_bands(bands or DEFAULT_BANDS)
    if any(a.ndim != 2 or a.dtype != np.uint8 for a in (hue, sat, value)) or hue.shape != sat.shape or hue.shape != value.shape:
        raise ValueError('H/S/V features must be matching uint8 planes')
    ih, iw = hue.shape
    if not 8 <= iw <= 640 or not 8 <= ih <= 480 or np.any(hue >= 180):
        raise ValueError('Invalid feature geometry or hue')
    sw, sh = source_size or (iw, ih)
    if sw <= 0 or sh <= 0:
        raise ValueError('Invalid source geometry')
    gains, quality = estimate_gains(hue, sat, value, calibration)
    x, y, w, height = p.roi
    x0, y0 = int(x * iw), int(y * ih)
    x1, y1 = min(iw, round((x+w)*iw)), min(ih, round((y+height)*ih))
    raw_h, raw_s, v = [np.ascontiguousarray(a[y0:y1, x0:x1]) for a in (hue, sat, value)]
    # Allow real dark-green colour evidence in shadows, with a bounded noise floor.
    lib = native_ops()
    if lib is not None:
        values=np.empty(2,np.float64)
        if lib.f3p_adaptive_value_stats(v.ctypes.data,v.shape[1],v.shape[0],v.strides[0],values.ctypes.data):raise ValueError('Invalid value plane')
        dark_level,mean_value=map(float,values)
    else:dark_level=float(np.percentile(v[::4,::4],10));mean_value=float(np.mean(v))
    floor = min(p.min_value, max(12, round(dark_level * .2)))
    key = tuple(bands[c] for c in COLORS)
    table, costs = _hue_tables(key)
    bounds = None
    if lib is not None:
        lut = classification_table(gains, key, saturation_floors(p))
        if not hasattr(_scratch, 'corrected') or _scratch.corrected.shape != (2,)+v.shape:
            _scratch.corrected = np.empty((2,)+v.shape, np.uint8)
            _scratch.bounds = np.empty((4,4), np.int32)
        corrected = _scratch.corrected
        # These masks belong to the returned result. Never reuse their storage:
        # callers may retain an earlier result while processing the next frame.
        planes = np.empty((4,)+v.shape, np.uint8)
        bounds = _scratch.bounds
        rc = lib.f3p_adaptive_classify(raw_h.ctypes.data, raw_s.ctypes.data, v.ctypes.data,
                  v.shape[1], v.shape[0], lut.ctypes.data, floor, corrected.ctypes.data, planes.ctypes.data, bounds.ctypes.data)
        if rc: raise ValueError('Invalid cached colour features: '+str(rc))
        h, s = corrected
    else:
        ht, st = correction_table(gains)
        h, s = ht[raw_h, raw_s], st[raw_h, raw_s]
        classes = cv.LUT(h, table)
        floors = np.asarray((255,) + saturation_floors(p), np.uint8)
        classes = np.where((v >= floor) & (s >= floors[classes]), classes, 0).astype(np.uint8)
    morph = getattr(lib, 'f3p_lighting_morph', None) if lib is not None else None
    mask_stats = getattr(lib, 'f3p_lighting_mask_stats', None) if lib is not None else None
    if not hasattr(_scratch, 'kernel'):
        _scratch.kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE, (3, 3))
    kernel = _scratch.kernel
    detections, masks, rejected = [], {}, 0
    sx, sy = sw / iw, sh / ih
    for ci, color in enumerate(COLORS):
        mask = planes[ci] if lib is not None else cv.compare(classes, ci + 1, cv.CMP_EQ)
        if bounds is not None:
            lx,ly,rx,ry=map(int,bounds[ci])
        else:
            lx,ly,bw,bh=cv.boundingRect(mask);rx,ry=lx+bw,ly+bh
        if lx>=rx or ly>=ry:
            masks[color]=mask
            continue
        lx,ly=max(0,lx-6),max(0,ly-6);rx,ry=min(mask.shape[1],rx+6),min(mask.shape[0],ry+6)
        section=mask[ly:ry,lx:rx]
        if morph is not None:
            required = 2*section.size
            if not hasattr(_scratch, 'morph_work') or _scratch.morph_work.size < required:
                _scratch.morph_work = np.empty(required, np.uint8)
            rc=morph(section.ctypes.data, section.strides[0], section.shape[1], section.shape[0],
                     _scratch.morph_work.ctypes.data, _scratch.morph_work.size)
            if rc:raise ValueError('Invalid colour morphology: '+str(rc))
        else:
            clean=cv.morphologyEx(section,cv.MORPH_OPEN,kernel)
            section[:]=cv.morphologyEx(clean,cv.MORPH_CLOSE,kernel,iterations=2)
        masks[color] = mask
        search,ox,oy=section,lx,ly
        if lib is not None and iw<=480 and ih<=270:
            if not hasattr(_scratch,'workspace'):
                _scratch.workspace=np.empty(480*270,np.uint32);_scratch.candidates=np.empty(480*270,np.uint8)
            candidates=_scratch.candidates[:section.size].reshape(section.shape)
            rc=lib.f3p_contour_candidates(section.ctypes.data,section.strides[0],candidates.ctypes.data,section.shape[1],section.shape[0],p.min_area*(iw/640.)**2,_scratch.workspace.ctypes.data,_scratch.workspace.size)
            if rc<0:raise ValueError('Invalid contour candidates')
            bx,by,bw,bh=cv.boundingRect(candidates)
            if not bw or not bh:continue
            search=candidates[by:by+bh,bx:bx+bw];ox+=bx;oy+=by
        for contour in cv.findContours(search, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE, offset=(ox,oy))[-2]:
            area = float(cv.contourArea(contour))
            if area < p.min_area * (iw/640.)**2:
                continue
            rect = cv.minAreaRect(contour)
            rw, rh = rect[1]
            fill = area / max(1., rw*rh)
            solidity = area / max(1., cv.contourArea(cv.convexHull(contour)))
            if (area > v.size*p.max_area_fraction or max(rw, rh)/max(1., min(rw, rh)) > p.max_aspect
                    or fill < p.min_rectangularity or solidity < p.min_solidity):
                rejected += 1
                continue
            bx, by, bw, bh = cv.boundingRect(contour)
            object_mask = np.zeros((bh, bw), np.uint8)
            cv.drawContours(object_mask, [contour], -1, 255, -1, offset=(-bx, -by))
            if lib is not None:
                hp,sp,vp=[a[by:by+bh,bx:bx+bw] for a in (h,s,v)]
                if mask_stats is not None:
                    selected=mask[by:by+bh,bx:bx+bw]
                    stats_fn=mask_stats
                else:
                    selected=np.where(mask[by:by+bh,bx:bx+bw]>0,ci+1,0).astype(np.uint8)
                    stats_fn=lib.f3p_lighting_stats
                cost,order=confidence_orders(key)[ci];stats=np.empty(6,np.float64)
                rc=stats_fn(hp.ctypes.data,sp.ctypes.data,vp.ctypes.data,h.strides[0],
                    selected.ctypes.data,selected.strides[0],object_mask.ctypes.data,bw,bh,ci+1,250,cost.ctypes.data,order.ctypes.data,stats.ctypes.data)
                if rc:raise ValueError('Invalid colour statistics: '+str(rc))
                hue_fit=1.-min(1.,float(stats[1]));chroma=float(stats[2])/255.;median_value=float(stats[3])
            else:
                use = (object_mask > 0) & (mask[by:by+bh, bx:bx+bw] > 0)
                hues, sats = h[by:by+bh, bx:bx+bw][use], s[by:by+bh, bx:bx+bw][use]
                hue_fit = 1. - min(1., float(np.median(costs[ci][hues])))
                chroma = float(np.median(sats)) / 255.
                median_value = float(np.median(v[by:by+bh, bx:bx+bw][use]))
            confidence = min(.99, max(0., .45*hue_fit+.25*chroma+.15*min(1., fill)+.15*min(1., solidity)))
            # Geometry alone does not establish a block's colour. Weak,
            # edge-of-band cardboard/neutral regions must remain unclassified.
            # Pale yellow loses saturation in glare. Accept weak hue evidence
            # only when the object is also bright relative to a valid neutral
            # reference; darker yellow-brown cardboard does not get this rescue.
            white_value = max(quality.get('white_bgr', [255.]))
            pale_yellow = (color == 'yellow' and quality['illumination_reference_valid']
                           and confidence >= .40 and hue_fit >= .2
                           and median_value >= .82*white_value)
            # Weak patches need a well-filled block outline. Pale yellow has
            # separate brightness evidence because shadows fragment its mask.
            if confidence < .55 and fill < max(p.min_rectangularity, .75) and not pale_yellow:
                rejected += 1
                continue
            if confidence < calibration.minimum_confidence and not pale_yellow:
                rejected += 1
                continue
            moments = cv.moments(contour)
            if moments['m00'] <= 0:
                continue
            points = cv.boxPoints(rect)
            points[:, 0] += x0
            points[:, 1] += y0
            detections.append({'color': color, 'label': LABELS[color],
                'center': [round((moments['m10']/moments['m00']+x0)*sx, 2), round((moments['m01']/moments['m00']+y0)*sy, 2)],
                'bbox': [round((bx+x0)*sx, 2), round((by+y0)*sy, 2), round(bw*sx, 2), round(bh*sy, 2)],
                'polygon': [[round(float(px)*sx, 2), round(float(py)*sy, 2)] for px, py in points],
                'area_px': round(area*sx*sy, 2), 'working_area_px': round(area, 2),
                'confidence': round(confidence, 3), 'rectangularity': round(fill, 3), 'solidity': round(solidity, 3)})
    detections.sort(key=lambda d: (-d['area_px'], d['color'], d['center'][0]))
    detections = detections[:32]
    quality.update(effective_min_value=floor, mean_brightness=round(mean_value, 1),
                   low_light=mean_value < 45, processor='adaptive_hs_candidate',
                   rgb_video_frames_copied=0)
    return dict(detections=detections, counts={c: sum(d['color']==c for d in detections) for c in COLORS},
                source_size=[sw, sh], analysis_size=[iw, ih],
                roi=[round(x0*sx), round(y0*sy), round((x1-x0)*sx), round((y1-y0)*sy)],
                roi_origin=[x0, y0], masks=masks, rejected_shapes=rejected, quality=quality)


def detect_image(frame, parameters=None, bands=None, source_size=None):
    cv, np = dependencies()
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
        raise ValueError('An 8-bit BGR image is required')
    hsv = canonical_hsv(cv.GaussianBlur(frame, (3, 3), 0))
    return detect_features(hsv[:, :, 0], hsv[:, :, 1], np.max(frame, axis=2), parameters, bands, source_size)


_scratch = threading.local()


@lru_cache(maxsize=1)
def native_ops():
    try:lib = ctypes.CDLL(str(Path(__file__).with_name('lighting_feature_access.so')))
    except OSError:return None
    lib.f3p_lighting_decode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint32]
    lib.f3p_lighting_decode.restype = ctypes.c_int
    ptr,integer=ctypes.c_void_p,ctypes.c_int
    lib.f3p_adaptive_classify.argtypes=[ptr,ptr,ptr,integer,integer,ptr,integer,ptr,ptr,ptr]
    lib.f3p_adaptive_classify.restype=integer
    lib.f3p_lighting_stats.argtypes=[ptr,ptr,ptr,integer,ptr,integer,ptr,integer,integer,integer,integer,ptr,ptr,ptr]
    lib.f3p_lighting_stats.restype=integer
    # Optional functions preserve compatibility with the installed older .so.
    if hasattr(lib, 'f3p_lighting_mask_stats'):
        lib.f3p_lighting_mask_stats.argtypes=lib.f3p_lighting_stats.argtypes
        lib.f3p_lighting_mask_stats.restype=integer
    if hasattr(lib, 'f3p_lighting_morph'):
        lib.f3p_lighting_morph.argtypes=[ptr,integer,integer,integer,ptr,ctypes.c_size_t]
        lib.f3p_lighting_morph.restype=integer
    lib.f3p_adaptive_white.argtypes=[ptr,ptr,ctypes.c_size_t,integer,integer,ptr]
    lib.f3p_adaptive_white.restype=integer
    lib.f3p_adaptive_value_stats.argtypes=[ptr,integer,integer,integer,ptr]
    lib.f3p_adaptive_value_stats.restype=integer
    lib.f3p_contour_candidates.argtypes=[ptr,integer,ptr,integer,integer,ctypes.c_double,ptr,ctypes.c_size_t]
    lib.f3p_contour_candidates.restype=integer
    return lib


def analyze_features(item, parameters, bands):
    _, np = dependencies()
    compact = item['compact']
    if compact.dtype != np.uint32 or compact.shape != (270, 780) or compact.strides != (3120, 4):
        raise ValueError('Unsupported compact geometry')
    if not hasattr(_scratch, 'planes'):
        _scratch.planes = np.empty((3, 270, 480), np.uint8)
    planes = _scratch.planes
    started = time.monotonic()
    lib=native_ops()
    if lib is None:raise RuntimeError('Lighting native decoder is not available')
    rc = lib.f3p_lighting_decode(compact.ctypes.data, planes.ctypes.data, planes.nbytes,
                                      480, 270, 780, item['frame_id'])
    if rc:
        raise RuntimeError('Invalid or incoherent lighting features: '+str(rc))
    decoded = time.monotonic()
    result = detect_features(*planes, parameters, bands, (1920, 1080))
    result['quality']['feature_decode_ms'] = round((decoded-started)*1000, 3)
    return result
