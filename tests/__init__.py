from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from station import Station
from station.bench.offline import FaultSchedule, OfflineBench


class StationCase(TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='thickness-test-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'station.sqlite'
        self.faults = FaultSchedule()
        self.station = self.open_connection(checkpoint=self.faults)
        self.bench = OfflineBench(self.station.shifts, namespace='test', checkpoint=self.faults)
        self.addCleanup(self.bench.close)
        self.capture = self.station.attach(self.bench)

    def open_connection(self, **options):
        station = Station(self.path, **options)
        self.addCleanup(station.close)
        return station

    def open_shift(self, shift_id='A', specimens=('P', 'Q', 'R')):
        return self.station.shifts.open(shift_id, specimens, (3, 1), (2, -2), 2)

    def mount(self, specimen='P', shift='A'):
        return self.bench.emit('mount', shift_id=shift, specimen_id=specimen)

    def edge(self, kind, exposure_id, head):
        return self.bench.emit(kind, exposure_id=exposure_id, head=head)

    def prepare(self, specimen='P', shift='A', codes=(3, 7)):
        self.mount(specimen, shift)
        exposures = {head: self.bench.request_measurement(head) for head in ('left', 'right')}
        for (head, exposure_id), code in zip(exposures.items(), codes, strict=True):
            self.edge('open', exposure_id, head)
            self.edge('close', exposure_id, head)
            self.bench.record(exposure_id, code)
        self.bench.emit('unmount')
        return exposures

    def deliver(self, exposure_id):
        return self.capture.admit(self.bench.deliver_reply(exposure_id))

    def capture_pair(self, exposures):
        for head in ('right', 'left'):
            self.deliver(exposures[head])

    def reading(self, exposure_id, *, station=None):
        station = self.station if station is None else station
        with station.database.read() as connection:
            return station.raw.by_exposure(connection, exposure_id)

    def pending(self, *, station=None):
        station = self.station if station is None else station
        with station.database.read() as connection:
            return station.confirmations.pending(connection)
