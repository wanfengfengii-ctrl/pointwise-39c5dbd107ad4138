from station.bench.events import BenchEvent
from tests import StationCase


class TestBench(StationCase):
    def test_occupied(self):
        self.open_shift()
        self.assertEqual(self.mount(), ('A', 'P'))
        with self.assertRaises(ValueError):
            self.mount('Q')
        self.assertEqual(self.bench.fixture.current_specimen(), ('A', 'P'))
        self.assertEqual(self.bench.adapter.last_position, 1)
        exposure = self.bench.exposure(self.bench.request_measurement('left'))
        self.assertEqual((exposure.exposure_id, exposure.shift_id, exposure.specimen_id, exposure.head),
                         ('test-000001', 'A', 'P', 'left'))

    def test_unknown_specimen(self):
        self.open_shift()
        with self.assertRaises(KeyError):
            self.mount('unlisted')
        with self.assertRaises(KeyError):
            self.mount('P', 'unknown')
        self.assertIsNone(self.bench.fixture.current_specimen())
        self.assertEqual(self.bench.adapter.last_position, 0)
        self.assertEqual(self.mount('Q'), ('A', 'Q'))

    def test_measurement_gate(self):
        self.open_shift()
        with self.assertRaises(ValueError):
            self.bench.request_measurement('left')
        self.mount()
        with self.assertRaises(ValueError):
            self.bench.request_measurement('centre')
        left = self.bench.request_measurement('left')
        with self.assertRaises(ValueError):
            self.bench.request_measurement('left')
        right = self.bench.request_measurement('right')
        self.assertEqual((left, right), ('test-000001', 'test-000002'))
        with self.assertRaises(ValueError):
            self.bench.emit('unmount')
        self.edge('open', left, 'left')
        with self.assertRaises(ValueError):
            self.bench.emit('unmount')
        with self.assertRaises(ValueError):
            self.bench.record(left, 3)
        self.edge('close', left, 'left')
        with self.assertRaises(ValueError):
            self.bench.emit('unmount')
        self.edge('open', right, 'right')
        self.edge('close', right, 'right')
        self.assertEqual(self.bench.emit('unmount'), ('A', 'P'))
        self.assertEqual(self.bench.record(left, 3).specimen_id, 'P')
        self.mount()
        with self.assertRaises(ValueError):
            self.bench.request_measurement('right')
        self.assertEqual(self.bench.emit('unmount'), ('A', 'P'))
        self.assertIsNone(self.bench.fixture.current_specimen())

    def test_invalid_edges(self):
        self.open_shift()
        self.mount()
        exposure = self.bench.request_measurement('left')
        rejects = (
            (ValueError, BenchEvent(3, 'open', exposure_id=exposure, head='left')),
            (ValueError, BenchEvent(2, 'close', exposure_id=exposure, head='left')),
            (ValueError, BenchEvent(2, 'open', exposure_id=exposure, head='right')),
            (KeyError, BenchEvent(2, 'open', exposure_id='unknown', head='left')),
        )
        for error, event in rejects:
            with self.subTest(event=event), self.assertRaises(error):
                self.bench.apply(event)
        self.assertEqual(self.bench.exposure(exposure).phase, 'requested')
        self.assertEqual(self.bench.adapter.last_position, 1)
        self.assertEqual(self.bench.adapter.exposure_edges(exposure), ())
        self.edge('open', exposure, 'left')
        with self.assertRaises(ValueError):
            self.edge('open', exposure, 'left')
        self.edge('close', exposure, 'left')
        with self.assertRaises(ValueError):
            self.edge('close', exposure, 'left')
        self.assertEqual(tuple(event.position for event in self.bench.adapter.exposure_edges(exposure)), (2, 3))
        self.assertEqual(self.bench.exposures.completed_heads('A', 'P'), {'left'})
