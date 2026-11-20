from dataclasses import dataclass

from station.handover.lookup import HandoverItem


@dataclass(frozen=True, slots=True)
class HandoverSheet:
    shift_id: str
    items: tuple[HandoverItem, ...]


class ShiftHandover:
    def __init__(self, database, registry, results, lookup):
        self._database = database
        self._registry = registry
        self._results = results
        self._lookup = lookup

    def collect(self, shift_id):
        with self._database.read() as connection:
            shift = self._registry.get(shift_id, connection=connection)
            results = self._results.for_shift(connection, shift_id)
            by_specimen = {result.specimen_id: result for result in results}
            items = tuple(
                self._lookup.from_snapshot(connection, by_specimen[specimen_id])
                for specimen_id in shift.roster.specimens if specimen_id in by_specimen
            )
            return HandoverSheet(shift_id, items)
