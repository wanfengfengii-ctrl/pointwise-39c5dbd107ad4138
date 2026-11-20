from dataclasses import dataclass

from station.bench.exposure import HEADS
from station.setup.roster import validate_identifier


@dataclass(frozen=True, slots=True)
class BenchEvent:
    position: int
    kind: str
    shift_id: str | None = None
    specimen_id: str | None = None
    exposure_id: str | None = None
    head: str | None = None


class BenchEventAdapter:
    def __init__(self, fixture, exposures, replies):
        self._fixture = fixture
        self._exposures = exposures
        self._replies = replies
        self._last_position = 0
        self._edges: dict[str, list[BenchEvent]] = {}

    @property
    def last_position(self):
        return self._last_position

    def apply(self, event: BenchEvent):
        if not isinstance(event, BenchEvent):
            raise ValueError('expected a bench event')
        if type(event.position) is not int or event.position != self._last_position + 1:
            raise ValueError('physical event must use the next device position')
        if event.kind == 'mount':
            if event.exposure_id is not None or event.head is not None:
                raise ValueError('mount cannot carry exposure details')
            result = self._fixture.mount(event.shift_id, event.specimen_id)
        elif event.kind == 'unmount':
            if any(value is not None for value in (
                event.shift_id, event.specimen_id, event.exposure_id, event.head
            )):
                raise ValueError('unmount takes no identity fields')
            result = self._fixture.unmount()
        elif event.kind in ('open', 'close'):
            result = self._apply_edge(event)
        else:
            raise ValueError(f'unknown physical event {event.kind!r}')
        self._last_position = event.position
        return result

    def request_measurement(self, head):
        specimen = self._fixture.current_specimen()
        if specimen is None:
            raise ValueError('fixture is empty')
        return self._exposures.request(*specimen, head).exposure_id

    def deliver_reply(self, exposure_id):
        return self._replies.get(exposure_id)

    def exposure_edges(self, exposure_id):
        return tuple(self._edges.get(exposure_id, ()))

    def release_edges(self, exposure_id):
        self._edges.pop(exposure_id, None)

    def _apply_edge(self, event):
        if event.shift_id is not None or event.specimen_id is not None or event.head not in HEADS:
            raise ValueError('an exposure edge requires an exposure ID and head')
        exposure_id = validate_identifier(event.exposure_id, 'exposure ID')
        exposure = self._exposures.find(exposure_id)
        if exposure is None:
            raise KeyError(exposure_id)
        if exposure.head != event.head:
            raise ValueError('edge head differs from requested head')
        if self._fixture.current_specimen() != (exposure.shift_id, exposure.specimen_id):
            raise ValueError('edge does not belong to the current fixed specimen')
        if event.kind == 'open':
            result = self._exposures.open_edge(exposure_id)
        else:
            result = self._exposures.close_edge(exposure_id)
        self._edges.setdefault(exposure_id, []).append(event)
        return result
