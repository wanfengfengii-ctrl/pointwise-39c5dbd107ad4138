from station.setup.roster import validate_identifier


class AcknowledgementWorker:
    def __init__(self, database, queue, source):
        self._database = database
        self._queue = queue
        self._source = source

    def confirm_exposure(self, exposure_id):
        validate_identifier(exposure_id, 'exposure ID')
        with self._database.read() as connection:
            pending = self._queue.pending(connection, exposure_id)
        if not pending:
            return False
        self._source.confirm(exposure_id)
        with self._database.write('ack') as connection:
            self._queue.mark_confirmed(connection, exposure_id)
        return True

    def retry_pending(self):
        with self._database.read() as connection:
            pending = self._queue.pending(connection)
        processed = []
        for exposure_id in pending:
            if self.confirm_exposure(exposure_id):
                processed.append(exposure_id)
        return tuple(processed)
