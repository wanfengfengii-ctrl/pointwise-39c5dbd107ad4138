from station.bench.confirmation import SourceConfirmation
from station.bench.events import BenchEvent, BenchEventAdapter
from station.bench.exposure import ExposureLedger
from station.bench.fixture import Fixture
from station.bench.recording import ReplyBuffer
from station.setup.database import InjectedFailure


class FaultSchedule:
    def __init__(self):
        self._armed: set[str] = set()

    def arm(self, point):
        self._armed.add(point)

    def __call__(self, point):
        if point in self._armed:
            self._armed.remove(point)
            raise InjectedFailure(point)


class OfflineBench:
    def __init__(self, shifts, *, namespace=None, checkpoint=None):
        self.exposures = ExposureLedger(namespace)
        self.fixture = Fixture(shifts, self.exposures)
        self.replies = ReplyBuffer(self.exposures)
        self.adapter = BenchEventAdapter(self.fixture, self.exposures, self.replies)
        self.confirmation = SourceConfirmation(
            self.replies, self.exposures, self.adapter.release_edges, checkpoint=checkpoint
        )
        self._closed = False

    def emit(self, kind, *, shift_id=None, specimen_id=None, exposure_id=None, head=None):
        event = BenchEvent(
            self.adapter.last_position + 1, kind, shift_id, specimen_id, exposure_id, head
        )
        return self.apply(event)

    def apply(self, event):
        self._require_online()
        return self.adapter.apply(event)

    def request_measurement(self, head):
        self._require_online()
        return self.adapter.request_measurement(head)

    def record(self, exposure_id, raw_code):
        self._require_online()
        return self.replies.record(exposure_id, raw_code)

    def deliver_reply(self, exposure_id):
        self._require_online()
        return self.adapter.deliver_reply(exposure_id)

    def exposure(self, exposure_id):
        self._require_online()
        return self.exposures.find(exposure_id)

    def confirm(self, exposure_id):
        self._require_online()
        self.confirmation.confirm(exposure_id)

    def close(self):
        self._closed = True

    def _require_online(self):
        if self._closed:
            raise RuntimeError('device source is closed')
