from dataclasses import dataclass

from station.quality.convert import HeadValues


@dataclass(frozen=True, slots=True)
class ThicknessDecision:
    difference_um: int
    accepted: bool


def classify_difference(values: HeadValues, tolerance: int) -> ThicknessDecision:
    difference = values.right_um - values.left_um
    return ThicknessDecision(difference, abs(difference) <= tolerance)
