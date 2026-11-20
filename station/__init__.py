from station.capture.acknowledge import AcknowledgementWorker
from station.capture.admit import CaptureAdmission
from station.capture.pending import ConfirmationQueue
from station.capture.raw_store import RawStore
from station.handover.lookup import ResultLookup
from station.handover.sheet import ShiftHandover
from station.quality.issue import QualityIssuer
from station.quality.result_store import ResultStore
from station.setup.database import StationDatabase
from station.setup.registry import ShiftRegistry
from station.visit.admit import VisitCaptureAdmission
from station.visit.issue import VisitIssuer
from station.visit.lookup import VisitLookup
from station.visit.pending import VisitConfirmationQueue
from station.visit.raw_store import VisitRawStore
from station.visit.registry import VisitRegistry
from station.visit.result_store import VisitResultStore


class Station:
    def __init__(self, path, *, checkpoint=None):
        self.database = StationDatabase(path, checkpoint=checkpoint)
        self.shifts = ShiftRegistry(self.database)
        self.raw = RawStore()
        self.confirmations = ConfirmationQueue()
        self.results = ResultStore()
        self.visit_raw = VisitRawStore()
        self.visit_confirmations = VisitConfirmationQueue()
        self.visit_results = VisitResultStore()
        self.visit_registry = VisitRegistry(self.database)
        try:
            self.database.initialize(
                self.shifts.install_schema,
                self.raw.install_schema,
                self.confirmations.install_schema,
                self.results.install_schema,
                VisitRegistry.install_schema,
                self.visit_raw.install_schema,
                self.visit_confirmations.install_schema,
                self.visit_results.install_schema,
            )
        except BaseException:
            self.database.close()
            raise
        self.quality = QualityIssuer(self.database, self.shifts, self.raw, self.results)
        self.visit_quality = VisitIssuer(
            self.database, self.shifts, self.visit_registry,
            self.visit_raw, self.visit_results,
        )
        self.quality.issue_visit = self.visit_quality.issue_visit
        self.lookup = ResultLookup(self.database, self.results, self.raw)
        self.visit_lookup = VisitLookup(self.database, self.visit_results, self.visit_raw)
        self.lookup.collect_visit = self.visit_lookup.collect_visit
        self.handover = ShiftHandover(self.database, self.shifts, self.results, self.lookup)

    def attach(self, source):
        if getattr(source, 'visit_mode', False):
            return VisitCaptureAdmission(
                self.database, self.visit_raw, self.visit_confirmations, source
            )
        worker = AcknowledgementWorker(self.database, self.confirmations, source)
        return CaptureAdmission(self.database, self.raw, self.confirmations, source, worker)

    def close(self):
        self.database.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
