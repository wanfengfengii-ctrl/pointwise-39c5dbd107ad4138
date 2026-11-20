from collections.abc import Sequence
from dataclasses import dataclass


def validate_identifier(value, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{label} must be nonempty text without NUL')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError(f'{label} must be valid Unicode text') from error
    return value


@dataclass(frozen=True, slots=True)
class SpecimenRoster:
    specimens: tuple[str, ...]

    def contains(self, specimen_id: str) -> bool:
        return specimen_id in self.specimens


def build_roster(specimens) -> SpecimenRoster:
    if not isinstance(specimens, Sequence) or isinstance(specimens, (str, bytes, bytearray)):
        raise ValueError('roster must be an ordered sequence of specimen IDs')
    entries = tuple(specimens)
    if not entries:
        raise ValueError('roster is empty')
    for specimen_id in entries:
        validate_identifier(specimen_id, 'specimen ID')
    if len(set(entries)) != len(entries):
        raise ValueError('duplicate specimen ID')
    return SpecimenRoster(entries)
