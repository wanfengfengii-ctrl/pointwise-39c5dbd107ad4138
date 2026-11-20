from dataclasses import dataclass

from station.handover.reconcile import verify_result_sources
from station.handover.source_rows import SourceRow, read_source_rows
from station.quality.result_store import IssuedResult


@dataclass(frozen=True, slots=True)
class HandoverItem:
    result: IssuedResult
    sources: tuple[SourceRow, ...]


class ResultLookup:
    def __init__(self, database, results, raw_store):
        self._database = database
        self._results = results
        self._raw = raw_store

    def collect(self, number):
        with self._database.read() as connection:
            result = self._results.by_number(connection, number)
            if result is None:
                raise KeyError(number)
            return self.from_snapshot(connection, result)

    def from_snapshot(self, connection, result):
        sources = read_source_rows(connection, self._raw, result.sources)
        verify_result_sources(result, sources)
        return HandoverItem(result, sources)
