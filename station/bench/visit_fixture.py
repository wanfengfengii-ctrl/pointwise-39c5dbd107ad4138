class VisitFixture:
    """Seat state for visit benches.

    Every mount starts a new visit and unmount is allowed whenever the seat is
    occupied, even with unfinished or invalid exposures.
    """

    def __init__(self, shifts, visits, ledger):
        self._shifts = shifts
        self._visits = visits
        self._ledger = ledger
        self._current: tuple[str, str, str] | None = None

    def mount(self, shift_id, specimen_id):
        if self._current is not None:
            raise ValueError('fixture is occupied')
        self._shifts.require_specimen(shift_id, specimen_id)
        visit_id = self._ledger.next_visit_id()
        self._visits.register(visit_id, shift_id, specimen_id)
        self._current = (visit_id, shift_id, specimen_id)
        return visit_id

    def unmount(self):
        if self._current is None:
            raise ValueError('fixture is empty')
        previous = self._current
        self._current = None
        return previous

    def current(self):
        return self._current
