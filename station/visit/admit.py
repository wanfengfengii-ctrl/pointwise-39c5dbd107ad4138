from station.bench.recording import RawReply
from station.capture.acknowledge import AcknowledgementWorker
from station.setup.roster import validate_identifier


def check_visit_reply_identity(reply: RawReply, exposure) -> None:
    if type(reply.raw_code) is not int:
        raise ValueError('raw code must be an integer')
    if reply.head != exposure.head:
        raise ValueError(f'reply head differs from exposure {exposure.exposure_id!r}')
    if (reply.shift_id, reply.specimen_id) != (exposure.shift_id, exposure.specimen_id):
        raise ValueError(f'reply identity differs from exposure {exposure.exposure_id!r}')


class VisitCaptureAdmission:
    """Takes over original replies for visit benches.

    Evidence needed to decide qualification (visit binding, validity, edge
    positions, raw code) is committed before the device is asked to reclaim
    the original package.
    """

    def __init__(self, database, raw_store, queue, source):
        self._database = database
        self._raw = raw_store
        self._queue = queue
        self._source = source
        self.acknowledgements = AcknowledgementWorker(database, queue, source)

    def admit(self, reply: RawReply):
        if not isinstance(reply, RawReply):
            raise ValueError('expected an original device reply')
        if type(reply.raw_code) is not int:
            raise ValueError('raw code must be an integer')
        exposure_id = validate_identifier(reply.exposure_id, 'exposure ID')
        with self._database.write('admit') as connection:
            reading = self._raw.by_exposure(connection, exposure_id)
            if reading is None:
                receipt = self._take_original(connection, reply)
            else:
                exposure = self._source.exposure(exposure_id)
                if exposure is not None:
                    check_visit_reply_identity(reply, exposure)
                self._check_stored_identity(reply, reading)
                receipt = reading.receipt
        self.acknowledgements.confirm_exposure(exposure_id)
        return receipt

    def _take_original(self, connection, reply):
        exposure = self._source.exposure(reply.exposure_id)
        if exposure is None:
            raise KeyError(reply.exposure_id)
        if exposure.close_position is None:
            raise ValueError('cannot accept a reply for an unfinished exposure')
        check_visit_reply_identity(reply, exposure)
        original = self._source.deliver_reply(reply.exposure_id)
        if original != reply:
            raise ValueError(
                f'reply differs from the buffered original for {reply.exposure_id!r}'
            )
        receipt = self._raw.insert(connection, exposure, reply.raw_code)
        self._queue.enqueue(connection, reply.exposure_id)
        return receipt

    @staticmethod
    def _check_stored_identity(reply, reading):
        if (reply.shift_id, reply.specimen_id, reply.head) != (
            reading.shift_id, reading.specimen_id, reading.head
        ):
            raise ValueError(f'reply identity differs from exposure {reply.exposure_id!r}')
        if reply.raw_code != reading.raw_code:
            raise ValueError(f'conflicting raw code for {reply.exposure_id!r}')
