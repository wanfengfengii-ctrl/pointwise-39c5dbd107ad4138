from dataclasses import replace

from station.bench.events import BenchEvent
from station.bench.offline import OfflineBench
from station.quality.eligibility import HeadCoverage
from station.setup.database import InjectedFailure
from tests import StationCase


class VisitCase(StationCase):
    def open_visit_bench(self, namespace='visit', **options):
        bench = OfflineBench(
            self.station.shifts, namespace=namespace,
            checkpoint=self.faults, visit_mode=True, **options
        )
        self.addCleanup(bench.close)
        return bench

    def mount(self, bench, specimen='P', shift='A'):
        return bench.emit('mount', shift_id=shift, specimen_id=specimen)

    def edge(self, bench, kind, exposure_id, head):
        return bench.emit(kind, exposure_id=exposure_id, head=head)

    def cycle(self, bench, exposure_id, head, code=None):
        self.edge(bench, 'open', exposure_id, head)
        self.edge(bench, 'close', exposure_id, head)
        if code is not None:
            return bench.record(exposure_id, code)
        return None

    def admit(self, bench, capture, exposure_id):
        return capture.admit(bench.deliver_reply(exposure_id))

    def coverage(self, visit_id):
        return self.station.quality.issue_visit(visit_id)


class TestVisitLifecycle(VisitCase):
    def test_each_mount_mints_a_unique_visit(self):
        self.open_shift()
        bench = self.open_visit_bench()
        first = self.mount(bench)
        self.assertIsInstance(first, str)
        self.assertTrue(first)
        bench.emit('unmount')
        second = self.mount(bench)
        self.assertNotEqual(first, second)
        with self.station.database.read() as connection:
            rows = connection.execute(
                'SELECT visit_id, shift_id, specimen_id FROM visits ORDER BY visit_id'
            ).fetchall()
        self.assertEqual([tuple(row) for row in rows],
                         [(first, 'A', 'P'), (second, 'A', 'P')])

    def test_occupied_mount_and_empty_unmount_are_rejected(self):
        self.open_shift()
        bench = self.open_visit_bench()
        self.mount(bench)
        with self.assertRaises(ValueError):
            self.mount(bench, 'Q')
        self.assertEqual(bench.fixture.current()[1:], ('A', 'P'))
        bench.emit('unmount')
        with self.assertRaises(ValueError):
            bench.emit('unmount')
        # Rejected events never consume a device position.
        self.assertEqual(bench.adapter.last_position, 2)
        self.assertEqual(bench.fixture.current(), None)
        self.mount(bench, 'Q')
        self.assertEqual(bench.fixture.current()[2], 'Q')

    def test_unmount_allowed_with_one_head_or_open_exposure(self):
        self.open_shift()
        bench = self.open_visit_bench()
        visit = self.mount(bench)
        self.edge(bench, 'open', 'v-L', 'left')
        self.edge(bench, 'close', 'v-L', 'left')
        bench.emit('unmount')
        second = self.mount(bench)
        self.edge(bench, 'open', 'v-R', 'right')
        bench.emit('unmount')  # open exposure never closed
        self.assertIsNone(bench.fixture.current())
        self.assertEqual(self.coverage(visit), HeadCoverage('missing', 'missing'))
        self.assertEqual(self.coverage(second), HeadCoverage('missing', 'missing'))

    def test_mount_rejects_unknown_roster_identity(self):
        self.open_shift()
        bench = self.open_visit_bench()
        with self.assertRaises(KeyError):
            bench.emit('mount', shift_id='A', specimen_id='unlisted')
        with self.assertRaises(KeyError):
            bench.emit('mount', shift_id='unknown', specimen_id='P')
        self.assertEqual(bench.adapter.last_position, 0)
        self.assertIsNone(bench.fixture.current())

    def test_request_measurement_is_not_a_visit_entry(self):
        self.open_shift()
        bench = self.open_visit_bench()
        self.mount(bench)
        with self.assertRaises(ValueError):
            bench.request_measurement('left')


class TestVisitEdges(VisitCase):
    def test_mounts_and_edges_share_one_device_sequence(self):
        self.open_shift()
        bench = self.open_visit_bench()
        visit = self.mount(bench)
        self.assertEqual(bench.adapter.last_position, 1)
        self.edge(bench, 'open', 'v-L', 'left')
        self.edge(bench, 'close', 'v-L', 'left')
        positions = [event.position for event in bench.adapter.exposure_edges('v-L')]
        self.assertEqual(positions, [2, 3])
        bench.emit('unmount')
        self.assertEqual(bench.adapter.last_position, 4)
        self.assertEqual(visit, bench.exposure('v-L').visit_id)

    def test_rejected_event_keeps_state_and_position(self):
        self.open_shift()
        bench = self.open_visit_bench()
        self.mount(bench)
        self.edge(bench, 'open', 'v-L', 'left')
        bad_events = (
            BenchEvent(3, 'close', exposure_id='v-L', head='right'),
            BenchEvent(3, 'open', exposure_id='v-L', head='left'),
            BenchEvent(3, 'open', exposure_id='v-R', head='centre'),
        )
        for event in bad_events:
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    bench.apply(event)
        with self.assertRaises(KeyError):
            bench.apply(BenchEvent(3, 'close', exposure_id='ghost', head='right'))
        self.assertEqual(bench.adapter.last_position, 2)
        self.assertIsNone(bench.exposure('v-L').close_position)
        self.assertEqual(bench.adapter.exposure_edges('v-L'),
                         (BenchEvent(2, 'open', exposure_id='v-L', head='left'),))

    def test_one_open_per_head_per_visit_even_after_unmount(self):
        self.open_shift()
        bench = self.open_visit_bench()
        first = self.mount(bench)
        self.edge(bench, 'open', 'v-L1', 'left')
        self.edge(bench, 'close', 'v-L1', 'left')
        bench.emit('unmount')
        second = self.mount(bench)
        self.edge(bench, 'open', 'v-L2', 'left')  # new visit, head usable again
        self.assertEqual(bench.exposure('v-L1').visit_id, first)
        self.assertEqual(bench.exposure('v-L2').visit_id, second)
        with self.assertRaises(ValueError):
            self.edge(bench, 'open', 'v-L2', 'left')  # exposure id never reused
        with self.assertRaises(ValueError):
            self.edge(bench, 'open', 'v-L1', 'left')

    def test_close_rules(self):
        self.open_shift()
        bench = self.open_visit_bench()
        self.mount(bench)
        with self.assertRaises(KeyError):
            self.edge(bench, 'close', 'missing', 'left')
        self.edge(bench, 'open', 'v-L', 'left')
        with self.assertRaises(ValueError):
            self.edge(bench, 'close', 'v-L', 'right')
        self.edge(bench, 'close', 'v-L', 'left')
        with self.assertRaises(ValueError):
            self.edge(bench, 'close', 'v-L', 'left')

    def test_cross_unmount_exposure_is_invalid_but_bound_to_opening_visit(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        first = self.mount(bench)
        self.edge(bench, 'open', 'span-L', 'left')
        bench.emit('unmount')
        second = self.mount(bench)
        self.edge(bench, 'close', 'span-L', 'left')
        exposure = bench.exposure('span-L')
        self.assertEqual(exposure.visit_id, first)
        self.assertFalse(exposure.valid)
        capture.admit(bench.record('span-L', 3))
        self.assertEqual(self.coverage(first), HeadCoverage('invalid', 'missing'))
        self.assertEqual(self.coverage(second), HeadCoverage('missing', 'missing'))

    def test_continuous_exposure_is_valid(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        visit = self.mount(bench)
        self.cycle(bench, 'v-L', 'left', 3)
        capture.admit(bench.deliver_reply('v-L'))
        self.assertEqual(self.coverage(visit), HeadCoverage('ready', 'missing'))

    def test_empty_seat_open_has_no_visit(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        self.edge(bench, 'open', 'empty-L', 'left')
        visit = self.mount(bench)
        self.edge(bench, 'close', 'empty-L', 'left')
        reply = bench.record('empty-L', 5)
        self.assertIsNone(reply.shift_id)
        self.assertIsNone(reply.specimen_id)
        capture.admit(reply)
        with self.assertRaises(KeyError):
            bench.deliver_reply('empty-L')
        self.assertEqual(self.coverage(visit), HeadCoverage('missing', 'missing'))
        with self.station.database.read() as connection:
            row = connection.execute(
                'SELECT visit_id, valid FROM visit_readings WHERE exposure_id = ?',
                ('empty-L',),
            ).fetchone()
        self.assertIsNone(row['visit_id'])
        self.assertEqual(row['valid'], 0)


class TestVisitAdmission(VisitCase):
    def test_reclaim_after_takeover_and_replay_receipt(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        self.mount(bench)
        reply = self.cycle(bench, 'v-L', 'left', 3)
        receipt = capture.admit(reply)
        self.assertEqual(receipt.exposure_id, 'v-L')
        with self.assertRaises(KeyError):
            bench.deliver_reply('v-L')
        self.assertIsNone(bench.exposure('v-L'))
        self.assertEqual(bench.adapter.exposure_edges('v-L'), ())
        self.assertTrue(bench.confirmation.is_confirmed('v-L'))
        self.assertEqual(capture.admit(reply), receipt)

    def test_conflicts_and_illegal_replies_keep_state(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        self.mount(bench)
        reply = self.cycle(bench, 'v-R', 'right', 7)
        for wrong in (
            replace(reply, raw_code=8), replace(reply, raw_code=True),
            replace(reply, raw_code=7.0), replace(reply, head='left'),
            replace(reply, shift_id='other'), replace(reply, specimen_id='Q'),
        ):
            with self.subTest(reply=wrong), self.assertRaises(ValueError):
                capture.admit(wrong)
        with self.assertRaises(KeyError):
            capture.admit(replace(reply, exposure_id='unknown'))
        self.assertEqual(bench.confirmation.attempts('v-R'), 0)
        self.assertEqual(bench.deliver_reply('v-R'), reply)
        with self.station.database.read() as connection:
            self.assertEqual(
                connection.execute('SELECT count(*) FROM visit_readings').fetchone()[0], 0
            )
        self.assertEqual(capture.admit(reply).exposure_id, 'v-R')

    def test_late_out_of_order_replies_after_reseat(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        first = self.mount(bench)
        first_left = self.cycle(bench, 'a-L', 'left', 3)
        bench.emit('unmount')
        second = self.mount(bench)
        second_right = self.cycle(bench, 'b-R', 'right', 7)
        capture.admit(second_right)
        capture.admit(first_left)
        self.assertEqual(self.coverage(first), HeadCoverage('ready', 'missing'))
        self.assertEqual(self.coverage(second), HeadCoverage('missing', 'ready'))

    def test_record_requires_closed_exposure_and_strict_integer(self):
        self.open_shift()
        bench = self.open_visit_bench()
        self.mount(bench)
        self.edge(bench, 'open', 'v-L', 'left')
        with self.assertRaises(ValueError):
            bench.record('v-L', 3)
        with self.assertRaises(KeyError):
            bench.record('missing', 3)
        self.edge(bench, 'close', 'v-L', 'left')
        with self.assertRaises(ValueError):
            bench.record('v-L', False)
        self.assertEqual(bench.record('v-L', 3), bench.record('v-L', 3))
        with self.assertRaises(ValueError):
            bench.record('v-L', 4)

    def test_admit_failure_does_not_confirm_and_remains_reusable(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        self.mount(bench)
        reply = self.cycle(bench, 'v-L', 'left', 3)
        self.faults.arm('admit.before_commit')
        with self.assertRaisesRegex(InjectedFailure, 'admit.before_commit'):
            capture.admit(reply)
        self.assertEqual(bench.confirmation.attempts('v-L'), 0)
        self.assertEqual(bench.deliver_reply('v-L'), reply)
        with self.station.database.read() as connection:
            self.assertEqual(
                connection.execute('SELECT count(*) FROM visit_readings').fetchone()[0], 0
            )
            self.assertEqual(tuple(self.station.visit_confirmations.pending(connection)), ())
        receipt = capture.admit(reply)
        self.assertTrue(bench.confirmation.is_confirmed('v-L'))
        self.assertEqual(capture.admit(reply), receipt)

    def test_source_failure_keeps_pending_confirmation_retryable(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        self.mount(bench)
        reply = self.cycle(bench, 'v-L', 'left', 3)
        self.faults.arm('source.before_confirm')
        with self.assertRaisesRegex(InjectedFailure, 'source.before_confirm'):
            capture.admit(reply)
        with self.station.database.read() as connection:
            self.assertEqual(
                self.station.visit_confirmations.pending(connection), ('v-L',)
            )
        self.assertEqual(bench.deliver_reply('v-L'), reply)
        self.assertEqual(capture.acknowledgements.retry_pending(), ('v-L',))
        self.assertEqual(capture.admit(reply).exposure_id, 'v-L')
        self.assertEqual(capture.acknowledgements.retry_pending(), ())


class TestVisitIssue(VisitCase):
    def _ready_visit(self, bench, capture, left_code=3, right_code=7):
        visit = self.mount(bench)
        capture.admit(self.cycle(bench, f'{visit}-L', 'left', left_code))
        capture.admit(self.cycle(bench, f'{visit}-R', 'right', right_code))
        return visit

    def test_coverage_states_and_visit_isolation(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        first = self.mount(bench)
        self.assertEqual(self.coverage(first), HeadCoverage('missing', 'missing'))
        capture.admit(self.cycle(bench, 'x-L', 'left', 3))
        self.assertEqual(self.coverage(first), HeadCoverage('ready', 'missing'))
        # An invalid right cannot become ready and blocks the head for its visit.
        bench.emit('unmount')  # position 4
        second = self.mount(bench)  # position 5
        self.edge(bench, 'open', 'x-R', 'right')  # position 6, belongs to second
        bench.emit('unmount')  # position 7, exposure left open across the seat change
        third = self.mount(bench)  # position 8
        self.edge(bench, 'close', 'x-R', 'right')  # position 9 -> invalid, bound to second
        capture.admit(bench.record('x-R', 7))
        self.assertEqual(self.coverage(second), HeadCoverage('missing', 'invalid'))
        self.assertEqual(self.coverage(third), HeadCoverage('missing', 'missing'))
        self.assertFalse(hasattr(self.coverage(first), 'number'))

    def test_unknown_visit_raises_key_error(self):
        self.open_shift()
        with self.assertRaises(KeyError):
            self.station.quality.issue_visit('no-such-visit')

    def test_atomic_issue_with_frozen_calibration_and_positions(self):
        self.station.shifts.open('A', ('P',), (1, 7), (2, -2), 2)
        bench = self.open_visit_bench(namespace='calc')
        capture = self.station.attach(bench)
        visit = self._ready_visit(bench, capture, left_code=4, right_code=7)
        result = self.station.quality.issue_visit(visit)
        self.assertEqual(
            (result.number, result.visit_id, result.shift_id, result.specimen_id),
            (1, visit, 'A', 'P'),
        )
        self.assertEqual(
            (result.left_um, result.right_um, result.difference_um, result.accepted),
            (11, 12, 1, True),
        )
        self.assertEqual(
            [(s.head, s.open_position, s.close_position, s.raw_code) for s in result.sources],
            [('left', 2, 3, 4), ('right', 4, 5, 7)],
        )
        # Re-issue returns the same frozen result number.
        self.assertEqual(self.station.quality.issue_visit(visit), result)

    def test_invalid_head_prevents_issue_forever(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        first = self.mount(bench)
        self.edge(bench, 'open', 'bad-L', 'left')
        bench.emit('unmount')
        self.mount(bench)  # second visit: interrupted exposure closes here
        self.edge(bench, 'close', 'bad-L', 'left')
        capture.admit(bench.record('bad-L', 3))
        bench.emit('unmount')
        self.mount(bench)  # third visit owns the valid right head
        capture.admit(self.cycle(bench, 'ok-R', 'right', 7))
        self.assertEqual(
            self.station.quality.issue_visit(first), HeadCoverage('invalid', 'missing')
        )

    def test_failed_issue_leaves_no_result_and_retry_uses_same_evidence(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        visit = self._ready_visit(bench, capture)
        self.faults.arm('issue.before_commit')
        with self.assertRaisesRegex(InjectedFailure, 'issue.before_commit'):
            self.station.quality.issue_visit(visit)
        with self.station.database.read() as connection:
            self.assertEqual(
                connection.execute('SELECT count(*) FROM visit_results').fetchone()[0], 0
            )
        issued = self.station.quality.issue_visit(visit)
        self.assertEqual(self.station.quality.issue_visit(visit), issued)

    def test_reopen_station_and_collect_visit_by_number(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        visit = self._ready_visit(bench, capture)
        issued = self.station.quality.issue_visit(visit)
        bench.close()
        self.station.close()
        reopened = self.open_connection()
        collected = reopened.lookup.collect_visit(issued.number)
        self.assertEqual(collected, issued)
        with self.assertRaises(KeyError):
            reopened.lookup.collect_visit(issued.number + 1)
        with self.assertRaises(ValueError):
            reopened.lookup.collect_visit(True)

    def test_source_restart_rebinds_and_reissues_by_visit_number(self):
        self.open_shift()
        bench = self.open_visit_bench()
        capture = self.station.attach(bench)
        visit = self.mount(bench)
        replies = {}
        for head, exposure, code in (('left', 'rb-L', 3), ('right', 'rb-R', 7)):
            self.cycle(bench, exposure, head, code)
            replies[head] = bench.deliver_reply(exposure)
        self.faults.arm('source.before_confirm')
        with self.assertRaises(InjectedFailure):
            capture.admit(replies['right'])
        capture.admit(replies['left'])
        bench.emit('unmount')
        self.station.close()
        # Same physical device reopens with a new station database connection.
        reopened = self.open_connection(checkpoint=self.faults)
        bench.bind_database(reopened.database)
        recapture = reopened.attach(bench)
        self.assertEqual(recapture.acknowledgements.retry_pending(), ('rb-R',))
        self.assertEqual(recapture.admit(replies['right']).exposure_id, 'rb-R')
        self.assertEqual(recapture.acknowledgements.retry_pending(), ())
        issued = reopened.quality.issue_visit(visit)
        self.assertEqual(
            (issued.left_um, issued.right_um, issued.difference_um, issued.accepted),
            (10, 12, 2, True),  # default shift calibration: 3x+1 and 2x-2
        )
        bench.close()
        reopened.close()
        again = self.open_connection()
        self.assertEqual(again.lookup.collect_visit(issued.number), issued)
