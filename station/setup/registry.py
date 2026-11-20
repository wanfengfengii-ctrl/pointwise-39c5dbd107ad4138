from station.setup.database import decode_integer, encode_integer
from station.setup.roster import validate_identifier
from station.setup.shift import freeze_shift, same_shift_definition


class ShiftRegistry:
    def __init__(self, database):
        self._database = database

    @property
    def database(self):
        return self._database

    @staticmethod
    def install_schema(connection):
        connection.execute('''
            CREATE TABLE IF NOT EXISTS shifts (
                shift_id TEXT PRIMARY KEY NOT NULL,
                left_multiplier TEXT NOT NULL,
                left_offset TEXT NOT NULL,
                right_multiplier TEXT NOT NULL,
                right_offset TEXT NOT NULL,
                tolerance TEXT NOT NULL
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS roster_entries (
                shift_id TEXT NOT NULL REFERENCES shifts(shift_id),
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                specimen_id TEXT NOT NULL,
                PRIMARY KEY (shift_id, ordinal),
                UNIQUE (shift_id, specimen_id)
            )
        ''')

    def open(self, shift_id, specimens, left, right, tolerance):
        definition = freeze_shift(shift_id, specimens, left, right, tolerance)
        with self._database.write('open_shift') as connection:
            existing = self._find(connection, definition.shift_id)
            if existing is not None:
                if not same_shift_definition(existing, definition):
                    raise ValueError(f'conflicting open request for shift {shift_id!r}')
                return existing.receipt
            self._insert(connection, definition)
            return definition.receipt

    def get(self, shift_id, *, connection=None):
        validate_identifier(shift_id, 'shift ID')
        if connection is None:
            with self._database.read() as snapshot:
                return self.get(shift_id, connection=snapshot)
        shift = self._find(connection, shift_id)
        if shift is None:
            raise KeyError(shift_id)
        return shift

    def require_specimen(self, shift_id, specimen_id, *, connection=None):
        validate_identifier(specimen_id, 'specimen ID')
        shift = self.get(shift_id, connection=connection)
        if not shift.roster.contains(specimen_id):
            raise KeyError((shift_id, specimen_id))
        return shift

    @staticmethod
    def _find(connection, shift_id):
        row = connection.execute(
            'SELECT * FROM shifts WHERE shift_id = ?', (shift_id,)
        ).fetchone()
        if row is None:
            return None
        roster = connection.execute('''
            SELECT specimen_id FROM roster_entries
            WHERE shift_id = ? ORDER BY ordinal
        ''', (shift_id,))
        return freeze_shift(
            shift_id,
            tuple(entry['specimen_id'] for entry in roster),
            (decode_integer(row['left_multiplier']), decode_integer(row['left_offset'])),
            (decode_integer(row['right_multiplier']), decode_integer(row['right_offset'])),
            decode_integer(row['tolerance']),
        )

    @staticmethod
    def _insert(connection, definition):
        calibration = definition.calibration
        connection.execute('''
            INSERT INTO shifts (
                shift_id, left_multiplier, left_offset, right_multiplier, right_offset, tolerance
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            definition.shift_id,
            encode_integer(calibration.left.multiplier),
            encode_integer(calibration.left.offset),
            encode_integer(calibration.right.multiplier),
            encode_integer(calibration.right.offset),
            encode_integer(calibration.tolerance),
        ))
        connection.executemany('''
            INSERT INTO roster_entries (shift_id, ordinal, specimen_id) VALUES (?, ?, ?)
        ''', (
            (definition.shift_id, ordinal, specimen)
            for ordinal, specimen in enumerate(definition.roster.specimens)
        ))
