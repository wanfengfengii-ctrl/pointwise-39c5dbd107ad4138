from station.bench.confirmation import SourceConfirmation
from station.bench.events import BenchEvent, BenchEventAdapter
from station.bench.exposure import ExposureLedger
from station.bench.fixture import Fixture
from station.bench.recording import ReplyBuffer
from station.bench.visit_events import VisitEventAdapter, VisitReplyBuffer
from station.bench.visit_exposure import VisitExposureLedger
from station.bench.visit_fixture import VisitFixture
from station.setup.database import InjectedFailure
from station.visit.registry import VisitRegistry


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
    def __init__(self, shifts, *, namespace=None, checkpoint=None, visit_mode=False):
        self._visit_mode = visit_mode
        self._closed = False
        if visit_mode:
            namespace = 'bench' if namespace is None else namespace
            self.exposures = VisitExposureLedger(namespace)
            self.visits = VisitRegistry(shifts.database)
            self.fixture = VisitFixture(shifts, self.visits, self.exposures)
            self.replies = VisitReplyBuffer(self.exposures)
            self.adapter = VisitEventAdapter(self.fixture, self.exposures, self.replies)
        else:
            self.exposures = ExposureLedger(namespace)
            self.fixture = Fixture(shifts, self.exposures)
            self.replies = ReplyBuffer(self.exposures)
            self.adapter = BenchEventAdapter(self.fixture, self.exposures, self.replies)
        self.confirmation = SourceConfirmation(
            self.replies, self.exposures, self.adapter.release_edges, checkpoint=checkpoint
        )

    @property
    def visit_mode(self):
        return self._visit_mode

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
        if self._visit_mode:
            raise ValueError('visit benches receive exposure edges directly')
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

    def bind_database(self, database):
        """Rebind persisted collaborators after the station database reopens."""
        from station.setup.registry import ShiftRegistry

        shifts = ShiftRegistry(database)
        if self._visit_mode:
            self.visits = VisitRegistry(database)
            self.fixture = VisitFixture(shifts, self.visits, self.exposures)
            self.adapter = VisitEventAdapter(self.fixture, self.exposures, self.replies)
        else:
            self.fixture = Fixture(shifts, self.exposures)
            self.adapter = BenchEventAdapter(self.fixture, self.exposures, self.replies)
        self.confirmation = SourceConfirmation(
            self.replies, self.exposures, self.adapter.release_edges,
            checkpoint=self.confirmation.checkpoint,
        )

    def close(self):
        self._closed = True

    def _require_online(self):
        if self._closed:
            raise RuntimeError('device source is closed')
