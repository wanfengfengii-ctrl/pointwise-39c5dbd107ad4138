from station.bench.exposure import HEADS
from station.handover.source_rows import EvidenceError


class VisitLookup:
    def __init__(self, database, results, raw_store):
        self._database = database
        self._results = results
        self._raw = raw_store

    def collect_visit(self, number):
        with self._database.read() as connection:
            result = self._results.by_number(connection, number)
            if result is None:
                raise KeyError(number)
            self._verify(connection, result)
            return result

    def _verify(self, connection, result):
        if len(result.sources) != len(HEADS):
            raise EvidenceError(f'visit result {result.number} requires two ordered sources')
        for source in result.sources:
            reading = self._raw.by_exposure(connection, source.exposure_id)
            if reading is None:
                raise EvidenceError(f'missing raw source {source.exposure_id!r}')
            expected = (
                result.visit_id, source.exposure_id, source.head,
                source.open_position, source.close_position, source.raw_code,
            )
            observed = (
                reading.visit_id, reading.exposure_id, reading.head,
                reading.open_position, reading.close_position, reading.raw_code,
            )
            if expected != observed:
                raise EvidenceError(
                    f'raw source {source.exposure_id!r} does not match result {result.number}'
                )
            if not reading.valid:
                raise EvidenceError(
                    f'raw source {source.exposure_id!r} is not a valid visit reading'
                )
