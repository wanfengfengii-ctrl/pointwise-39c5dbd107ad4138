from contextlib import closing
import sqlite3

from station.handover.source_rows import EvidenceError
from station.setup.database import InjectedFailure
from tests import StationCase


class TestHandover(StationCase):
    def test_failed_issue_then_offline(self):
        self.open_shift()
        exposures = self.prepare()
        self.capture_pair(exposures)
        self.faults.arm('issue.before_commit')
        with self.assertRaisesRegex(InjectedFailure, 'issue.before_commit'):
            self.station.quality.issue('A', 'P')
        self.assertEqual(self.station.handover.collect('A').items, ())
        with self.assertRaises(KeyError):
            self.station.lookup.collect(1)
        issued = self.station.quality.issue('A', 'P')
        self.bench.close()
        self.station.close()
        reopened = self.open_connection()
        item = reopened.lookup.collect(issued.number)
        self.assertEqual(item.result, issued)
        self.assertEqual((item.result.left_um, item.result.right_um, item.result.difference_um,
                          item.result.accepted), (10, 12, 2, True))
        self.assertEqual(tuple((source.shift_id, source.specimen_id, source.head, source.exposure_id,
                                source.raw_code) for source in item.sources), (
            ('A', 'P', 'left', exposures['left'], 3),
            ('A', 'P', 'right', exposures['right'], 7),
        ))

    def test_rollback_visibility(self):
        self.open_shift(specimens=('P', 'Q'))
        self.capture_pair(self.prepare('Q', codes=(4, 6)))
        older = self.station.quality.issue('A', 'Q')
        self.capture_pair(self.prepare())
        observed = []

        def checkpoint(point):
            if point != 'issue.after_result':
                return
            with closing(sqlite3.connect(self.path)) as observer:
                observed.append(observer.execute('''
                    SELECT (SELECT count(*) FROM issued_results),
                           (SELECT count(*) FROM result_sources)
                ''').fetchone())
            raise InjectedFailure(point)

        issuer = self.open_connection(checkpoint=checkpoint)
        with self.assertRaisesRegex(InjectedFailure, 'issue.after_result'):
            issuer.quality.issue('A', 'P')
        self.assertEqual(observed, [(1, 2)])
        self.assertEqual(tuple(item.result for item in self.station.handover.collect('A').items), (older,))
        self.assertEqual(self.station.lookup.collect(older.number).result, older)
        with self.assertRaises(KeyError):
            self.station.lookup.collect(older.number + 1)
        self.assertEqual(len(self.station.raw_for_test) if hasattr(self.station, 'raw_for_test') else 0, 0)
        completed = self.station.quality.issue('A', 'P')
        self.assertEqual(completed.number, older.number + 1)
        self.assertEqual(len(self.station.lookup.collect(completed.number).sources), 2)

    def test_repeat_issue(self):
        self.open_shift()
        self.capture_pair(self.prepare())
        first = self.station.quality.issue('A', 'P')
        self.assertEqual(self.station.quality.issue('A', 'P'), first)
        reopened = self.open_connection()
        self.assertEqual(reopened.quality.issue('A', 'P'), first)
        self.assertEqual(len(reopened.handover.collect('A').items), 1)

    def test_fixed_sources(self):
        self.open_shift()
        first = self.prepare()
        self.capture_pair(first)
        issued = self.station.quality.issue('A', 'P')
        self.capture_pair(self.prepare('Q', codes=(19, 23)))
        self.bench.close()
        self.station.close()
        reopened = self.open_connection()
        item = reopened.lookup.collect(issued.number)
        self.assertEqual(item.result, issued)
        self.assertEqual(tuple((row.specimen_id, row.head, row.exposure_id, row.raw_code)
                               for row in item.sources), (
            ('P', 'left', first['left'], 3), ('P', 'right', first['right'], 7),
        ))

    def test_roster_order(self):
        self.open_shift()
        self.capture_pair(self.prepare('P'))
        self.capture_pair(self.prepare('Q', codes=(4, 6)))
        q = self.station.quality.issue('A', 'Q')
        p = self.station.quality.issue('A', 'P')
        sheet = self.station.handover.collect('A')
        self.assertLess(q.number, p.number)
        self.assertEqual(tuple(item.result for item in sheet.items), (p, q))
        self.assertEqual(tuple(item.sources[0].specimen_id for item in sheet.items), ('P', 'Q'))

    def test_empty_and_unknown(self):
        self.open_shift()
        sheet = self.station.handover.collect('A')
        self.assertEqual((sheet.shift_id, sheet.items), ('A', ()))
        with self.assertRaises(KeyError):
            self.station.handover.collect('missing')
        with self.assertRaises(KeyError):
            self.station.lookup.collect(1)
        with self.assertRaises(KeyError):
            self.station.lookup.collect(1 << 80)
        with self.assertRaises(ValueError):
            self.station.lookup.collect(True)

    def test_incomplete_fixed_references_are_rejected(self):
        self.open_shift()
        self.capture_pair(self.prepare())
        result = self.station.quality.issue('A', 'P')
        with self.station.database.write('damage_fixture') as connection:
            connection.execute('DELETE FROM result_sources WHERE number = ? AND head = ?',
                               (result.number, 'right'))
        reopened = self.open_connection()
        with self.assertRaises(EvidenceError):
            reopened.lookup.collect(result.number)
        with self.assertRaises(EvidenceError):
            reopened.handover.collect('A')
        with reopened.database.read() as connection:
            self.assertEqual(reopened.results.by_number(connection, result.number).difference_um, 2)
