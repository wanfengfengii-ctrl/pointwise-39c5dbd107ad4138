from dataclasses import dataclass

from station.setup.calibration import ShiftCalibration, build_calibration
from station.setup.roster import SpecimenRoster, build_roster, validate_identifier


@dataclass(frozen=True, slots=True)
class OpenShiftReceipt:
    shift_id: str


@dataclass(frozen=True, slots=True)
class FrozenShift:
    shift_id: str
    roster: SpecimenRoster
    calibration: ShiftCalibration

    @property
    def receipt(self) -> OpenShiftReceipt:
        return OpenShiftReceipt(self.shift_id)


def freeze_shift(shift_id, specimens, left, right, tolerance) -> FrozenShift:
    return FrozenShift(
        validate_identifier(shift_id, 'shift ID'),
        build_roster(specimens),
        build_calibration(left, right, tolerance),
    )


def same_shift_definition(first: FrozenShift, second: FrozenShift) -> bool:
    return first == second
