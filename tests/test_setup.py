from station.setup.shift import OpenShiftReceipt
from tests import StationCase


class TestSetup(StationCase):
    def test_open_and_repeat(self):
        supplied_roster = ['P', 'Q', 'R']
        first = self.open_shift(specimens=supplied_roster)
        supplied_roster.reverse()
        repeat = self.open_shift()
        self.assertEqual(first, OpenShiftReceipt('A'))
        self.assertEqual(repeat, first)
        self.assertEqual(self.station.shifts.get('A').roster.specimens, ('P', 'Q', 'R'))
        with self.station.database.read() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM shifts').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM roster_entries').fetchone()[0], 3)

    def test_conflict(self):
        original = self.open_shift()
        for right in ((8, -2), (2, 0)):
            with self.subTest(right=right), self.assertRaises(ValueError):
                self.station.shifts.open('A', ('P', 'Q', 'R'), (3, 1), right, 2)
        shift = self.station.shifts.get('A')
        self.assertEqual((shift.calibration.right.multiplier, shift.calibration.right.offset), (2, -2))
        self.assertEqual(shift.receipt, original)

    def test_roster_order(self):
        original = self.open_shift()
        with self.assertRaises(ValueError):
            self.open_shift(specimens=('Q', 'P', 'R'))
        self.assertEqual(self.station.shifts.get('A').roster.specimens, ('P', 'Q', 'R'))
        self.assertEqual(self.open_shift(), original)

    def test_invalid_input(self):
        cases = (
            ('A', (), (3, 1), (2, -2), 2),
            ('A', ('P', 'P'), (3, 1), (2, -2), 2),
            ('A', 'P', (3, 1), (2, -2), 2),
            ('A', {'P'}, (3, 1), (2, -2), 2),
            ('A', ('',), (3, 1), (2, -2), 2),
            ('A', (None,), (3, 1), (2, -2), 2),
            ('A', ('P',), (True, 1), (2, -2), 2),
            ('A', ('P',), (3, 1.0), (2, -2), 2),
            ('A', ('P',), (3, None), (2, -2), 2),
            ('A', ('P',), (3,), (2, -2), 2),
            ('A', ('P',), (3, 1), None, 2),
            ('A', ('P',), (3, 1), b'12', 2),
            ('A', ('P',), (3, 1), (2, -2), -1),
            ('A', ('P',), (3, 1), (2, -2), True),
            ('', ('P',), (3, 1), (2, -2), 2),
        )
        for inputs in cases:
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                self.station.shifts.open(*inputs)
        with self.assertRaises(KeyError):
            self.station.shifts.get('A')
        self.assertEqual(self.open_shift().shift_id, 'A')

    def test_init_reopen(self):
        receipt = self.open_shift(specimens=('S', 'P'))
        self.station.close()
        reopened = self.open_connection()
        self.assertEqual(reopened.shifts.open('A', ('S', 'P'), (3, 1), (2, -2), 2), receipt)
        self.assertEqual(reopened.shifts.get('A').roster.specimens, ('S', 'P'))
        self.assertEqual(reopened.shifts.open('B', ('Q',), (1, 0), (1, 0), 0).shift_id, 'B')
        self.assertEqual(reopened.shifts.get('A').calibration.tolerance, 2)
