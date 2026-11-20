from dataclasses import dataclass

from station.bench.exposure import HEADS
from station.capture.raw_store import RawReading


@dataclass(frozen=True, slots=True)
class HeadCoverage:
    left: str
    right: str

    @property
    def missing(self):
        return tuple(head for head in HEADS if getattr(self, head) == 'missing')


@dataclass(frozen=True, slots=True)
class EligiblePair:
    left: RawReading
    right: RawReading


def assess_eligibility(connection, raw_store, shift, specimen_id):
    readings = raw_store.for_specimen(connection, shift.shift_id, specimen_id)
    by_head = {reading.identity.head: reading for reading in readings}
    if all(head in by_head for head in HEADS):
        return EligiblePair(by_head['left'], by_head['right'])
    return HeadCoverage(*('ready' if head in by_head else 'missing' for head in HEADS))
