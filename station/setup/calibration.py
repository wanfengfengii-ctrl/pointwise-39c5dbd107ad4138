from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HeadCalibration:
    multiplier: int
    offset: int


@dataclass(frozen=True, slots=True)
class ShiftCalibration:
    left: HeadCalibration
    right: HeadCalibration
    tolerance: int


def _head_parameters(values, head):
    if not isinstance(values, Sequence) or len(values) != 2:
        raise ValueError(f'{head} calibration requires a multiplier and offset')
    if isinstance(values, (str, bytes, bytearray)):
        raise ValueError(f'{head} calibration requires an integer pair')
    multiplier, offset = values
    if type(multiplier) is not int or type(offset) is not int:
        raise ValueError(f'{head} calibration requires integers')
    return HeadCalibration(multiplier, offset)


def build_calibration(left, right, tolerance) -> ShiftCalibration:
    if type(tolerance) is not int or tolerance < 0:
        raise ValueError('tolerance must be a nonnegative integer')
    return ShiftCalibration(
        _head_parameters(left, 'left'),
        _head_parameters(right, 'right'),
        tolerance,
    )
