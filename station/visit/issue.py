from station.quality.classify import classify_difference
from station.quality.convert import convert_pair
from station.quality.eligibility import HeadCoverage
from station.visit.eligibility import assess_visit_eligibility


class VisitIssuer:
    def __init__(self, database, registry, visits, raw_store, results):
        self._database = database
        self._registry = registry
        self._visits = visits
        self._raw = raw_store
        self._results = results

    def issue_visit(self, visit_id):
        with self._database.write('issue') as connection:
            visit_row = self._visits.get(connection, visit_id)
            visit = (
                visit_row['visit_id'], visit_row['shift_id'], visit_row['specimen_id']
            )
            existing = self._results.by_visit(connection, visit_id)
            if existing is not None:
                return existing
            shift = self._registry.get(visit[1], connection=connection)
            eligibility = assess_visit_eligibility(connection, self._raw, visit_id)
            if isinstance(eligibility, HeadCoverage):
                return eligibility
            values = convert_pair(eligibility, shift.calibration)
            decision = classify_difference(values, shift.calibration.tolerance)
            return self._results.insert(
                connection, visit, values, decision, eligibility,
                after_header=lambda: self._database.checkpoint('issue.after_result'),
            )
