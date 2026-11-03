"""Camera OSD publisher for the offline candidate, not a board installer.

Uses an already owned Control.mem mapping. Does not acquire /dev/mem, change
video mode, copy RGB images, or produce robot-arm commands. Call publish only
after feature-slot/config checks and tracking complete. Full-screen UI wiring
is deliberately a separate integration step.
"""
import ctypes
import math

BASE = 0x1C0
CAPABILITY = 0x4F534431
COLORS = {"red": 0xFF4040, "green": 0x40FF60,
          "blue": 0x4080FF, "yellow": 0xFFFF40}


def encode_boxes(result, limit=16):
    """Map original result coordinates to native video without changing result."""
    sw, sh = result["source_size"]
    if not all(math.isfinite(float(v)) and v > 0 for v in (sw, sh)):
        raise ValueError("Invalid source geometry")
    encoded = []
    for detection in result.get("tracked", []):
        if not detection.get("stable"):
            continue
        color = COLORS.get(detection.get("color"))
        if color is None:
            continue
        x, y, width, height = map(float, detection["bbox"])
        if not all(math.isfinite(v) for v in (x, y, width, height)):
            raise ValueError("Non-finite result rectangle")
        if width <= 0 or height <= 0:
            continue
        x0 = max(0, min(1920, math.floor(x * 1920 / sw)))
        y0 = max(0, min(1080, math.floor(y * 1080 / sh)))
        x1 = max(0, min(1920, math.ceil((x + width) * 1920 / sw)))
        y1 = max(0, min(1080, math.ceil((y + height) * 1080 / sh)))
        if x0 < x1 and y0 < y1:
            encoded.append((x0 | y0 << 16, x1 | y1 << 16, color | 1 << 31))
    return encoded[:limit], max(0, len(encoded) - limit)


class ResultMailbox:
    """Nonblocking latest-result delivery; no backlog of historical boxes.

    Latest_source_id is the binary feature completed-ID at byte offset 0x388.
    Reject results >6 source frames old; PL also expires an accepted result
    after 250 ms of display-clock ticks. Frame IDs are metadata, not evidence
    that the displayed video frame has been analyzed.
    """
    def __init__(self, read_word, write_word):
        self.read = read_word
        self.write = write_word
        if self.read(BASE) != CAPABILITY:
            raise RuntimeError("OSD1 FPGA candidate is not installed")
        self.limit = self.read(BASE + 28)
        if not 1 <= self.limit <= 16:
            raise RuntimeError("Unsupported OSD rectangle count")
        self.last_frame_id = None
        self.sent = self.busy_drops = self.stale_drops = self.truncated = 0

    def _commit(self, frame_id, boxes):
        if self.read(BASE + 4) & 1:
            self.busy_drops += 1
            return False
        # The caller must serialize this publisher with itself. The camera
        # lease uses a different register; no extra writable MMIO map is made.
        self.write(BASE + 4, 0x4F530000)
        for index, (xy0, xy1, color) in enumerate(boxes):
            for offset, value in ((8, index), (12, xy0), (16, xy1), (20, color)):
                self.write(BASE + offset, value)
        self.write(BASE + 24, frame_id & 0xFFFFFFFF)
        self.write(BASE + 4, 0x4F530001)
        # This read flushes posted MMIO writes. Acknowledge is asynchronous.
        self.read(BASE + 4)
        self.sent += 1
        return True

    def publish(self, result, frame_id, latest_source_id):
        frame_id &= 0xFFFFFFFF
        if frame_id == self.last_frame_id:
            return False
        lag = (latest_source_id - frame_id) & 0xFFFFFFFF
        if lag > 6:
            self.stale_drops += 1
            return False
        boxes, truncated = encode_boxes(result, self.limit)
        if self._commit(frame_id, boxes):
            self.last_frame_id = frame_id
            self.truncated += truncated
            return True
        return False

    def clear(self):
        """Clear on parameter changes, stream recovery, failure, and exit.

        If busy, return False and retry on the next control tick. PL timeout
        provides the bound if the owner stops before a clear is acknowledged.
        """
        accepted = self._commit(self.last_frame_id or 0, [])
        if accepted:
            self.last_frame_id = None
        return accepted


def mapped_publisher(control):
    """Adapter to an existing exclusively owned camera Control mapping."""
    def read(offset):
        if offset not in range(BASE, BASE + 32, 4):
            raise ValueError("Outside OSD read aperture")
        # The existing native read helper rejects 0x1c0..0x1dc before its
        # barrier. Use an allowed camera read for dsb sy, then an aligned
        # uint32 access to the new aperture through the SAME owner mapping.
        control.read(0x33C)
        word = ctypes.c_uint32.from_buffer(control.mem, offset)
        try:
            return word.value
        finally:
            del word

    def write(offset, value):
        # Exact range + alignment guard prevents motion/audio/config writes.
        if offset not in range(BASE + 4, BASE + 28, 4):
            raise ValueError("Outside OSD staging aperture")
        word = ctypes.c_uint32.from_buffer(control.mem, offset)
        try:
            word.value = value
        finally:
            del word
        control.read(0x33C)  # Legal native read executes the existing dsb sy.
    return ResultMailbox(read, write)
