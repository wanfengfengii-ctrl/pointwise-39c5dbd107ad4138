from station.bench.events import BenchEvent
from station.bench.exposure import HEADS
from station.bench.recording import RawReply
from station.setup.roster import validate_identifier


class VisitReplyBuffer:
    """Device reply buffer for visit benches.

    Shift and specimen follow the identity captured at open time, so an empty
    seat open produces replies with both identity fields set to None.
    """

    def __init__(self, exposures):
        self._exposures = exposures
        self._replies: dict[str, RawReply] = {}

    def record(self, exposure_id, raw_code):
        if type(raw_code) is not int:
            raise ValueError('raw code must be an integer')
        exposure = self._exposures.find(exposure_id)
        if exposure is None:
            raise KeyError(exposure_id)
        if exposure.close_position is None:
            raise ValueError('exposure has not finished')
        previous = self._replies.get(exposure_id)
        if previous is not None:
            if previous.raw_code != raw_code:
                raise ValueError('device reply already has a different raw code')
            return previous
        reply = RawReply(
            exposure.exposure_id, exposure.shift_id, exposure.specimen_id,
            exposure.head, raw_code,
        )
        self._replies[exposure_id] = reply
        return reply

    def get(self, exposure_id):
        return self._replies[exposure_id]

    def release(self, exposure_id):
        self._replies.pop(exposure_id, None)


class VisitEventAdapter:
    """Physical event adapter for visit benches.

    Mounts, unmounts and open/close edges share one device sequence starting
    at one; each accepted event advances it by exactly one position.
    """

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
        current = self._fixture.current()
        current_visit_id = current[0] if current is not None else None
        if event.kind == 'open':
            result = self._exposures.open_edge(
                exposure_id, event.head, event.position, current
            )
        else:
            result = self._exposures.close_edge(
                exposure_id, event.head, event.position, current_visit_id
            )
        self._edges.setdefault(exposure_id, []).append(event)
        return result
