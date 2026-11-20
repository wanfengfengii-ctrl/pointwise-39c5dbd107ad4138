from dataclasses import dataclass, replace
from uuid import uuid4

from station.setup.roster import validate_identifier


HEADS = ('left', 'right')


@dataclass(frozen=True, slots=True)
class Exposure:
    exposure_id: str
    shift_id: str
    specimen_id: str
    head: str
    phase: str = 'requested'


class ExposureLedger:
    def __init__(self, namespace=None):
        self._namespace = uuid4().hex if namespace is None else validate_identifier(
            namespace, 'device namespace'
        )
        self._sequence = 0
        self._details: dict[str, Exposure] = {}
        self._requested: dict[tuple[str, str], set[str]] = {}
        self._completed: dict[tuple[str, str], set[str]] = {}

    def request(self, shift_id, specimen_id, head):
        if head not in HEADS:
            raise ValueError(f'unknown head {head!r}')
        specimen = (shift_id, specimen_id)
        requested = self._requested.setdefault(specimen, set())
        if head in requested:
            raise ValueError(f'{head} head already requested for {specimen!r}')
        self._sequence += 1
        exposure_id = f'{self._namespace}-{self._sequence:06d}'
        exposure = Exposure(exposure_id, shift_id, specimen_id, head)
        self._details[exposure_id] = exposure
        requested.add(head)
        return exposure

    def open_edge(self, exposure_id):
        return self._advance(exposure_id, 'requested', 'open')

    def close_edge(self, exposure_id):
        exposure = self._advance(exposure_id, 'open', 'closed')
        specimen = (exposure.shift_id, exposure.specimen_id)
        self._completed.setdefault(specimen, set()).add(exposure.head)
        return exposure

    def completed_heads(self, shift_id, specimen_id):
        return frozenset(self._completed.get((shift_id, specimen_id), ()))

    def find(self, exposure_id):
        return self._details.get(exposure_id)

    def release_details(self, exposure_id):
        self._details.pop(exposure_id, None)

    def _advance(self, exposure_id, previous, following):
        exposure = self.find(exposure_id)
        if exposure is None:
            raise KeyError(exposure_id)
        if exposure.phase != previous:
            raise ValueError(f'exposure {exposure_id!r} cannot advance from {exposure.phase!r}')
        advanced = replace(exposure, phase=following)
        self._details[exposure_id] = advanced
        return advanced
