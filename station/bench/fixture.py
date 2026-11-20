from station.bench.exposure import HEADS


class Fixture:
    def __init__(self, shifts, exposures):
        self._shifts = shifts
        self._exposures = exposures
        self._current: tuple[str, str] | None = None

    def mount(self, shift_id, specimen_id):
        if self._current is not None:
            raise ValueError('fixture is occupied')
        self._shifts.require_specimen(shift_id, specimen_id)
        self._current = (shift_id, specimen_id)
        return self._current

    def unmount(self):
        if self._current is None:
            raise ValueError('fixture is empty')
        specimen = self._current
        if self._exposures.completed_heads(*specimen) != frozenset(HEADS):
            raise ValueError('both heads must finish before unloading')
        self._current = None
        return specimen

    def current_specimen(self):
        return self._current
