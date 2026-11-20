from dataclasses import dataclass, replace

from station.setup.roster import validate_identifier


@dataclass(frozen=True, slots=True)
class VisitExposure:
    exposure_id: str
    head: str
    open_position: int
    close_position: int | None = None
    visit_id: str | None = None
    shift_id: str | None = None
    specimen_id: str | None = None
    valid: bool = False


class VisitExposureLedger:
    """Device-side exposure state for visit (unclamped) benches.

    An exposure is opened against the seat's current identity.  Opening on an
    empty seat has no visit; an open that spans an unmount stays bound to the
    original visit but is marked invalid once it closes.
    """

    def __init__(self, namespace):
        self._namespace = validate_identifier(namespace, 'device namespace')
        self._sequence = 0
        self._details: dict[str, VisitExposure] = {}
        self._used_heads: dict[str, set[str]] = {}
        self._open_by_head: dict[str, str] = {}

    def next_visit_id(self):
        self._sequence += 1
        return f'{self._namespace}-v{self._sequence:06d}'

    def find(self, exposure_id):
        return self._details.get(exposure_id)

    def open_edge(self, exposure_id, head, position, current):
        validate_identifier(exposure_id, 'exposure ID')
        if exposure_id in self._details:
            raise ValueError(f'exposure {exposure_id!r} cannot be reused')
        visit_id = current[0] if current is not None else None
        if visit_id is not None and head in self._used_heads.setdefault(visit_id, set()):
            raise ValueError(f'{head} head already opened during visit {visit_id!r}')
        exposure = VisitExposure(
            exposure_id, head, position, None, visit_id,
            current[1] if current is not None else None,
            current[2] if current is not None else None,
        )
        self._details[exposure_id] = exposure
        self._open_by_head[head] = exposure_id
        if visit_id is not None:
            self._used_heads[visit_id].add(head)
        return exposure

    def close_edge(self, exposure_id, head, position, current_visit_id):
        exposure = self.find(exposure_id)
        if exposure is None:
            raise KeyError(exposure_id)
        if exposure.head != head:
            raise ValueError('edge head differs from the opened exposure')
        if exposure.close_position is not None:
            raise ValueError(f'exposure {exposure_id!r} is already closed')
        valid = (
            exposure.visit_id is not None
            and exposure.visit_id == current_visit_id
        )
        closed = replace(exposure, close_position=position, valid=valid)
        self._details[exposure_id] = closed
        if self._open_by_head.get(head) == exposure_id:
            self._open_by_head.pop(head)
        return closed

    def release_details(self, exposure_id):
        self._details.pop(exposure_id, None)
