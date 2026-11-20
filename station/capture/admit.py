from station.bench.recording import RawReply
from station.capture.identity import check_reply_identity, identity_from_exposure
from station.setup.roster import validate_identifier


class CaptureAdmission:
    def __init__(self, database, raw_store, queue, source, acknowledgements):
        self._database = database
        self._raw = raw_store
        self._queue = queue
        self._source = source
        self.acknowledgements = acknowledgements

    def admit(self, reply: RawReply):
        if not isinstance(reply, RawReply):
            raise ValueError('expected an original device reply')
        exposure_id = validate_identifier(reply.exposure_id, 'exposure ID')
        with self._database.write('admit') as connection:
            reading = self._raw.by_exposure(connection, exposure_id)
            if reading is None:
                reading = self._take_original(connection, reply)
            else:
                check_reply_identity(reply, reading.identity)
                if reply.raw_code != reading.raw_code:
                    raise ValueError(f'conflicting raw code for {exposure_id!r}')
        self.acknowledgements.confirm_exposure(exposure_id)
        return reading.receipt

    def _take_original(self, connection, reply):
        exposure = self._source.exposure(reply.exposure_id)
        if exposure is None:
            raise KeyError(reply.exposure_id)
        identity = identity_from_exposure(exposure)
        check_reply_identity(reply, identity)
        original = self._source.deliver_reply(reply.exposure_id)
        if original != reply:
            raise ValueError(f'reply differs from the buffered original for {reply.exposure_id!r}')
        reading = self._raw.insert(connection, identity, reply.raw_code)
        self._queue.enqueue(connection, reply.exposure_id)
        return reading
