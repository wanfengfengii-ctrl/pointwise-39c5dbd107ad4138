import json

from station.quality.eligibility import HeadCoverage
from station.setup.database import InjectedFailure
from tests import StationCase


class TestDay(StationCase):
    def test_day_shift(self):
        self.open_shift()
        first = self.prepare()
        second = self.prepare('Q', codes=(4, 6))
        self.deliver(first['right'])
        self.assertEqual(self.station.quality.issue('A', 'P'), HeadCoverage('missing', 'ready'))
        self.capture_pair(second)
        q = self.station.quality.issue('A', 'Q')
        self.deliver(first['left'])
        self.faults.arm('issue.before_commit')
        with self.assertRaises(InjectedFailure):
            self.station.quality.issue('A', 'P')
        self.assertEqual(tuple(item.result.number for item in self.station.handover.collect('A').items),
                         (q.number,))
        p = self.station.quality.issue('A', 'P')
        self.assertEqual(p.number, q.number + 1)
        self.assertEqual(self.station.quality.issue('A', 'P'), p)
        self.bench.close()
        self.station.close()
        reopened = self.open_connection()
        with reopened.database.read() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM raw_readings').fetchone()[0], 4)
            self.assertEqual(connection.execute('SELECT count(*) FROM issued_results').fetchone()[0], 2)
        sheet = reopened.handover.collect('A')
        expected = [[10, 12, 2, True], [13, 10, -3, False]]
        actual = [[result.left_um, result.right_um, result.difference_um, result.accepted]
                  for result in (p, q)]
        self.assertEqual(actual, expected)
        self.assertEqual(tuple(item.result for item in sheet.items), (p, q))
        downstream_expected = [
            ['P', 'test-000001', 'test-000002', 3, 7],
            ['Q', 'test-000003', 'test-000004', 4, 6],
        ]
        downstream_actual = []
        for item in sheet.items:
            left, right = item.sources
            self.assertEqual(reopened.lookup.collect(item.result.number), item)
            downstream_actual.append([item.result.specimen_id, left.exposure_id, right.exposure_id,
                                      left.raw_code, right.raw_code])
        self.assertEqual(downstream_actual, downstream_expected)
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'n8',
            'input': {
                'roster': ['P', 'Q', 'R'], 'calibration': [[3, 1], [2, -2]], 'tolerance_um': 2,
                'codes_left_right': {'P': [3, 7], 'Q': [4, 6]}, 'issue_order': ['Q', 'P'],
                'failed_commit_before_P': True,
            },
            'expected': expected,
            'actual': actual,
            'downstream_expected': downstream_expected,
            'downstream_actual': downstream_actual,
            'code_paths': [
                'station/capture/admit.py', 'station/quality/issue.py', 'station/quality/result_store.py',
                'station/handover/sheet.py', 'station/handover/lookup.py',
            ],
            'oracle': 'Hand calculation of affine values and fixed source numbers in roster order.',
        }, sort_keys=True))
