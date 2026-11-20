from dataclasses import replace

from station.bench.recording import RawReply
from station.setup.database import InjectedFailure
from tests import StationCase


class TestCapture(StationCase):
    def test_reverse_replies(self):
        self.open_shift()
        exposures = self.prepare()
        self.capture_pair(exposures)
        observer = self.open_connection()
        left = self.reading(exposures['left'], station=observer)
        right = self.reading(exposures['right'], station=observer)
        self.assertEqual((left.identity.exposure_id, left.identity.head, left.raw_code),
                         ('test-000001', 'left', 3))
        self.assertEqual((right.identity.exposure_id, right.identity.head, right.raw_code),
                         ('test-000002', 'right', 7))
        self.assertLess(right.receipt.number, left.receipt.number)
        for exposure_id in exposures.values():
            self.assertTrue(self.bench.confirmation.is_confirmed(exposure_id))
            self.assertIsNone(self.bench.exposure(exposure_id))
            self.assertEqual(self.bench.adapter.exposure_edges(exposure_id), ())
            with self.assertRaises(KeyError):
                self.bench.deliver_reply(exposure_id)

    def test_late_after_unload(self):
        self.open_shift()
        first = self.prepare()
        self.mount('Q')
        late_reply = self.bench.deliver_reply(first['left'])
        self.assertEqual(late_reply.specimen_id, 'P')
        self.capture.admit(late_reply)
        self.assertEqual(self.reading(first['left']).identity.specimen_id, 'P')
        self.assertEqual(self.bench.fixture.current_specimen(), ('A', 'Q'))
        self.assertEqual(self.bench.deliver_reply(first['right']).specimen_id, 'P')

    def test_identity_errors(self):
        self.open_shift()
        exposures = self.prepare()
        reply = self.bench.deliver_reply(exposures['right'])
        for wrong in (replace(reply, shift_id='other'), replace(reply, specimen_id='Q'),
                      replace(reply, head='left'), replace(reply, raw_code=True),
                      replace(reply, raw_code=7.0), replace(reply, raw_code=None),
                      replace(reply, raw_code=8)):
            with self.subTest(reply=wrong), self.assertRaises(ValueError):
                self.capture.admit(wrong)
        with self.assertRaises(KeyError):
            self.capture.admit(replace(reply, exposure_id='unknown'))
        self.assertIsNone(self.reading(reply.exposure_id))
        self.assertEqual(self.pending(), ())
        self.assertEqual(self.bench.confirmation.attempts(reply.exposure_id), 0)
        self.mount('Q')
        unfinished = self.bench.request_measurement('right')
        with self.assertRaises(ValueError):
            self.capture.admit(RawReply(unfinished, 'A', 'Q', 'right', 7))
        self.assertIsNone(self.reading(unfinished))
        self.assertEqual(self.capture.admit(reply).exposure_id, reply.exposure_id)

    def test_repeat_and_conflict(self):
        self.open_shift()
        exposure = self.prepare()['right']
        reply = self.bench.deliver_reply(exposure)
        receipt = self.capture.admit(reply)
        self.assertEqual(self.capture.admit(reply), receipt)
        with self.assertRaises(ValueError):
            self.capture.admit(replace(reply, raw_code=8))
        self.assertEqual(self.reading(exposure).raw_code, 7)
        self.assertEqual(self.reading(exposure).receipt, receipt)
        self.assertEqual(self.bench.confirmation.attempts(exposure), 1)
        with self.station.database.read() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM raw_readings').fetchone()[0], 1)

    def test_identity_on_replay(self):
        self.open_shift()
        exposure = self.prepare()['right']
        reply = self.bench.deliver_reply(exposure)
        original = self.capture.admit(reply)
        with self.assertRaises(ValueError):
            self.capture.admit(replace(reply, specimen_id='Q'))
        with self.assertRaises(ValueError):
            self.capture.admit(replace(reply, head='left'))
        self.assertEqual(self.bench.confirmation.attempts(exposure), 1)
        self.assertEqual(self.reading(exposure).receipt, original)
        self.assertEqual(self.reading(exposure).identity.specimen_id, 'P')
        self.assertEqual(self.capture.admit(reply), original)

    def test_failed_write(self):
        self.open_shift()
        exposure = self.prepare()['right']
        observer = self.open_connection()
        reply = self.bench.deliver_reply(exposure)
        edges = self.bench.adapter.exposure_edges(exposure)
        self.faults.arm('admit.before_commit')
        with self.assertRaisesRegex(InjectedFailure, 'admit.before_commit'):
            self.capture.admit(reply)
        self.assertIsNone(self.reading(exposure, station=observer))
        self.assertEqual(self.pending(station=observer), ())
        self.assertEqual(self.bench.confirmation.attempts(exposure), 0)
        self.assertEqual(self.bench.deliver_reply(exposure), reply)
        self.assertEqual(self.bench.adapter.exposure_edges(exposure), edges)
        receipt = self.capture.admit(reply)
        self.assertEqual(self.reading(exposure, station=observer).receipt, receipt)
        self.assertEqual(self.bench.confirmation.attempts(exposure), 1)
        self.assertTrue(self.bench.confirmation.is_confirmed(exposure))
        self.assertEqual(self.bench.adapter.exposure_edges(exposure), ())
        with self.assertRaises(KeyError):
            self.bench.deliver_reply(exposure)

    def test_ack_retry(self):
        self.open_shift()
        exposure = self.prepare()['right']
        reply = self.bench.deliver_reply(exposure)
        self.faults.arm('source.before_confirm')
        with self.assertRaisesRegex(InjectedFailure, 'source.before_confirm'):
            self.capture.admit(reply)
        committed = self.reading(exposure)
        self.assertEqual(committed.raw_code, 7)
        self.assertEqual(self.pending(), (exposure,))
        self.assertEqual(self.bench.deliver_reply(exposure), reply)
        self.assertFalse(self.bench.confirmation.is_confirmed(exposure))
        self.station.close()
        restarted = self.open_connection()
        recapture = restarted.attach(self.bench)
        self.assertEqual(self.pending(station=restarted), (exposure,))
        self.assertEqual(recapture.acknowledgements.retry_pending(), (exposure,))
        self.assertEqual(recapture.admit(reply), committed.receipt)
        self.assertEqual(self.pending(station=restarted), ())
        self.assertEqual(self.bench.confirmation.attempts(exposure), 2)

    def test_ack_already_reclaimed(self):
        self.open_shift()
        exposure = self.prepare()['right']
        reply = self.bench.deliver_reply(exposure)
        self.faults.arm('source.after_reclaim')
        with self.assertRaisesRegex(InjectedFailure, 'source.after_reclaim'):
            self.capture.admit(reply)
        self.assertEqual(self.pending(), (exposure,))
        self.assertTrue(self.bench.confirmation.is_confirmed(exposure))
        self.assertIsNone(self.bench.exposure(exposure))
        self.assertEqual(self.bench.adapter.exposure_edges(exposure), ())
        with self.assertRaises(KeyError):
            self.bench.deliver_reply(exposure)
        self.assertEqual(self.capture.admit(reply), self.reading(exposure).receipt)
        self.assertEqual(self.pending(), ())
        self.assertEqual(self.bench.confirmation.attempts(exposure), 2)
        self.assertEqual(self.capture.acknowledgements.retry_pending(), ())

    def test_ack_local_write_failure(self):
        self.open_shift()
        exposure = self.prepare()['left']
        self.faults.arm('ack.before_commit')
        with self.assertRaisesRegex(InjectedFailure, 'ack.before_commit'):
            self.deliver(exposure)
        self.assertTrue(self.bench.confirmation.is_confirmed(exposure))
        self.assertEqual(self.pending(), (exposure,))
        self.assertEqual(self.reading(exposure).raw_code, 3)
        self.assertTrue(self.capture.acknowledgements.confirm_exposure(exposure))
        self.assertFalse(self.capture.acknowledgements.confirm_exposure(exposure))
        self.assertEqual(self.pending(), ())
