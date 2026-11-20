from station.quality.classify import classify_difference
from station.quality.convert import convert_pair
from station.quality.eligibility import HeadCoverage, assess_eligibility


class QualityIssuer:
    def __init__(self, database, registry, raw_store, results):
        self._database = database
        self._registry = registry
        self._raw = raw_store
        self._results = results

    def issue(self, shift_id, specimen_id):
        with self._database.write('issue') as connection:
            shift = self._registry.require_specimen(shift_id, specimen_id, connection=connection)
            existing = self._results.by_specimen(connection, shift_id, specimen_id)
            if existing is not None:
                return existing
            eligibility = assess_eligibility(connection, self._raw, shift, specimen_id)
            if isinstance(eligibility, HeadCoverage):
                return eligibility
            values = convert_pair(eligibility, shift.calibration)
            decision = classify_difference(values, shift.calibration.tolerance)
            return self._results.insert(
                connection, shift_id, specimen_id, values, decision, eligibility,
                after_header=lambda: self._database.checkpoint('issue.after_result'),
            )
