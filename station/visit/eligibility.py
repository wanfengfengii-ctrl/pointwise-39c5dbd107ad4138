from dataclasses import dataclass

from station.bench.exposure import HEADS
from station.quality.eligibility import HeadCoverage
from station.visit.raw_store import VisitReading


@dataclass(frozen=True, slots=True)
class VisitEligiblePair:
    left: VisitReading
    right: VisitReading


def assess_visit_eligibility(connection, raw_store, visit_id):
    readings = raw_store.for_visit(connection, visit_id)
    by_head = {reading.head: reading for reading in readings}

    def state(head):
        reading = by_head.get(head)
        if reading is None:
            return 'missing'
        return 'ready' if reading.valid else 'invalid'

    states = {head: state(head) for head in HEADS}
    if all(states[head] == 'ready' for head in HEADS):
        return VisitEligiblePair(by_head['left'], by_head['right'])
    return HeadCoverage(*(states[head] for head in HEADS))
