from dataclasses import dataclass

from station.setup.calibration import HeadCalibration, ShiftCalibration


@dataclass(frozen=True, slots=True)
class HeadValues:
    left_um: int
    right_um: int


def to_micrometres(raw_code: int, calibration: HeadCalibration) -> int:
    return calibration.multiplier * raw_code + calibration.offset


def convert_pair(pair, calibration: ShiftCalibration) -> HeadValues:
    return HeadValues(
        to_micrometres(pair.left.raw_code, calibration.left),
        to_micrometres(pair.right.raw_code, calibration.right),
    )
