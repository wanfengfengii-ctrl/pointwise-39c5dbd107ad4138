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


class Station:
    def __init__(self, path, *, checkpoint=None):
        self.database = StationDatabase(path, checkpoint=checkpoint)
        self.shifts = ShiftRegistry(self.database)
        self.raw = RawStore()
        self.confirmations = ConfirmationQueue()
        self.results = ResultStore()
        try:
            self.database.initialize(
                self.shifts.install_schema,
                self.raw.install_schema,
                self.confirmations.install_schema,
                self.results.install_schema,
            )
        except BaseException:
            self.database.close()
            raise
        self.quality = QualityIssuer(self.database, self.shifts, self.raw, self.results)
        self.lookup = ResultLookup(self.database, self.results, self.raw)
        self.handover = ShiftHandover(self.database, self.shifts, self.results, self.lookup)

    def attach(self, source):
        worker = AcknowledgementWorker(self.database, self.confirmations, source)
        return CaptureAdmission(self.database, self.raw, self.confirmations, source, worker)

    def close(self):
        self.database.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
