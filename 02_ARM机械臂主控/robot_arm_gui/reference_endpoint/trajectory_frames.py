"""Immutable packed trajectory frames; complete validation precedes FIFO execution."""
import hashlib
import math
import operator
import struct
from collections.abc import Sequence
from collections import OrderedDict
from types import MappingProxyType

_RECORD = struct.Struct('<I33d6i6H8B')
_FLOAT_FIELDS = (('t_s',1), ('command_t_s',1), ('reference_u',1),
    ('reference_xyz_mm',3), ('reference_joints_deg',6), ('reference_motor_deg',6),
    ('command_xyz_mm',3), ('command_joints_deg',6), ('command_motor_deg',6))
_INT_FIELDS = (('motor_target_pulses',6), ('speed_rpm',6), ('acceleration',6))

class _ReadOnlyVector(tuple):
    __slots__ = ()
    def __eq__(self, other):
        if isinstance(other, (tuple, list)):
            return tuple.__eq__(self, tuple(other))
        return NotImplemented
    def __ne__(self, other):
        equal = self.__eq__(other)
        return NotImplemented if equal is NotImplemented else not equal
    __hash__ = tuple.__hash__
    def __deepcopy__(self, memo):
        return self

class PackedFrames(Sequence):
    __slots__ = ('_data', '_sha', '_cache')
    RECORD_BYTES = _RECORD.size
    def __init__(self, data):
        if type(data) is not bytes or len(data) % _RECORD.size:
            raise ValueError('invalid packed trajectory payload')
        object.__setattr__(self, '_data', data)
        object.__setattr__(self, '_sha', hashlib.sha256(data).hexdigest())
        object.__setattr__(self, '_cache', OrderedDict())
    def __setattr__(self, name, value):
        raise TypeError('trajectory payload is immutable')
    def __len__(self):
        return len(self._data) // _RECORD.size
    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        index = operator.index(index)
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        cached = self._cache.get(index)
        if cached is not None:
            return cached
        values = _RECORD.unpack_from(self._data, index * _RECORD.size)
        result, offset = {'seq':values[0]}, 1
        for name, size in _FLOAT_FIELDS + _INT_FIELDS:
            result[name] = values[offset] if size == 1 else _ReadOnlyVector(values[offset:offset+size])
            offset += size
        result.update(phase='wrist_preparation' if values[offset] == 0 else 'cartesian', final=bool(values[offset+1]))
        result = MappingProxyType(result)
        self._cache[index] = result
        if len(self._cache) > 512:
            self._cache.popitem(last=False)
        return result
    def __deepcopy__(self, memo):
        return self
    def __eq__(self, other):
        if type(other) is PackedFrames:
            return self._data == other._data
        return NotImplemented
    def fingerprint(self):
        return {'packed_trajectory_schema':1, 'records':len(self),
                'record_bytes':_RECORD.size, 'sha256':self._sha}
    @property
    def storage_bytes(self):
        return len(self._data)

class FrameBuilder:
    def __init__(self):
        self._data = bytearray()
    def __len__(self):
        return len(self._data) // _RECORD.size
    def append(self, frame):
        values = [frame['seq']]
        for name, size in _FLOAT_FIELDS + _INT_FIELDS:
            part = [frame[name]] if size == 1 else frame[name]
            if len(part) != size:
                raise ValueError('invalid trajectory frame field: ' + name)
            values.extend(part)
        # One C-level iterator replaces thirteen per-field Python generators.
        # All fields are still checked before this record can be committed.
        if not all(map(math.isfinite, values[1:])):
            raise ValueError('invalid trajectory frame: non-finite field')
        if frame['phase'] not in ('wrist_preparation', 'cartesian') or type(frame['final']) is not bool:
            raise ValueError('invalid trajectory frame phase/final')
        values.extend((0 if frame['phase'] == 'wrist_preparation' else 1, int(frame['final'])))
        self._data.extend(_RECORD.pack(*values))
    def freeze(self):
        return PackedFrames(bytes(self._data))
