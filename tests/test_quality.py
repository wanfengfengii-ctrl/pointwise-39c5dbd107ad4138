from station.quality.eligibility import HeadCoverage
from station.setup.database import InjectedFailure
from tests import StationCase


class TestQuality(StationCase):
    def test_missing_then_threshold(self):
        self.open_shift()
        exposures = self.prepare()
        self.assertEqual(self.station.quality.issue('A', 'P'), HeadCoverage('missing', 'missing'))
        self.deliver(exposures['left'])
        incomplete = self.station.quality.issue('A', 'P')
        self.assertEqual(incomplete, HeadCoverage('ready', 'missing'))
        self.assertEqual(incomplete.missing, ('right',))
        self.assertFalse(hasattr(incomplete, 'number'))
        self.assertEqual(self.station.handover.collect('A').items, ())
        self.deliver(exposures['right'])
        result = self.station.quality.issue('A', 'P')
        self.assertEqual((result.left_um, result.right_um, result.difference_um), (10, 12, 2))
        self.assertIs(result.accepted, True)
        self.assertIs(self.station.lookup.collect(result.number).result.accepted, True)

    def test_shift_isolation(self):
        self.open_shift('A')
        self.open_shift('B')
        first = self.prepare(shift='A')
        second = self.prepare(shift='B', codes=(1, 20))
        self.deliver(second['right'])
        self.deliver(first['left'])
        for shift, expected in (('A', HeadCoverage('ready', 'missing')),
                                ('B', HeadCoverage('missing', 'ready'))):
            with self.subTest(shift=shift):
                coverage = self.station.quality.issue(shift, 'P')
                self.assertEqual(coverage, expected)
                self.assertFalse(hasattr(coverage, 'number'))
                self.assertEqual(self.station.handover.collect(shift).items, ())
        self.deliver(first['right'])
        self.assertEqual(self.station.quality.issue('A', 'P').difference_um, 2)
        self.assertEqual(self.station.quality.issue('B', 'P').missing, ('left',))

    def test_unknown_identity(self):
        self.open_shift()
        with self.assertRaises(KeyError):
            self.station.quality.issue('missing', 'P')
        with self.assertRaises(KeyError):
            self.station.quality.issue('A', 'unlisted')
        self.assertEqual(self.station.handover.collect('A').items, ())

    def test_affine_signed(self):
        self.open_shift()
        self.capture_pair(self.prepare(codes=(4, 6)))
        result = self.station.quality.issue('A', 'P')
        self.assertEqual((result.left_um, result.right_um, result.difference_um), (13, 10, -3))
        self.assertIs(result.accepted, False)
        item = self.station.lookup.collect(result.number)
        self.assertEqual(tuple(row.raw_code for row in item.sources), (4, 6))
        self.assertEqual(item.result.difference_um, -3)

    def test_exact_large_integers(self):
        large = 1 << 20000
        self.station.shifts.open('A', ('P',), (large, 1), (-1, large), 7)
        self.capture_pair(self.prepare(codes=(-1, 2 * large - 4)))
        result = self.station.quality.issue('A', 'P')
        self.assertIs(result.accepted, True)
        self.assertEqual(result.difference_um, 3)
        self.bench.close()
        self.station.close()
        with self.open_connection() as reopened:
            item = reopened.lookup.collect(result.number)
            self.assertTrue(item.result.left_um == 1 - large)
            self.assertTrue(item.result.right_um == 4 - large)
            self.assertEqual(item.result.difference_um, 3)
            self.assertTrue(item.sources[1].raw_code == 2 * large - 4)
            self.assertTrue(reopened.shifts.get('A').calibration.left.multiplier == large)

    def test_ack_pending(self):
        self.open_shift()
        exposures = self.prepare()
        self.deliver(exposures['right'])
        self.faults.arm('source.before_confirm')
        with self.assertRaises(InjectedFailure):
            self.deliver(exposures['left'])
        self.assertEqual(self.pending(), (exposures['left'],))
        result = self.station.quality.issue('A', 'P')
        self.assertEqual(result.difference_um, 2)
        self.assertEqual(self.capture.acknowledgements.retry_pending(), (exposures['left'],))
        self.assertEqual(self.station.quality.issue('A', 'P'), result)
