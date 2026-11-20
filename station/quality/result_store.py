from dataclasses import dataclass

from station.setup.database import decode_integer, encode_integer


@dataclass(frozen=True, slots=True)
class ResultSourceRef:
    head: str
    exposure_id: str


@dataclass(frozen=True, slots=True)
class IssuedResult:
    number: int
    shift_id: str
    specimen_id: str
    left_um: int
    right_um: int
    difference_um: int
    accepted: bool
    sources: tuple[ResultSourceRef, ...]


class ResultStore:
    @staticmethod
    def install_schema(connection):
        connection.execute('''
            CREATE TABLE IF NOT EXISTS issued_results (
                number INTEGER PRIMARY KEY,
                shift_id TEXT NOT NULL,
                specimen_id TEXT NOT NULL,
                left_um TEXT NOT NULL,
                right_um TEXT NOT NULL,
                difference_um TEXT NOT NULL,
                accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
                UNIQUE (shift_id, specimen_id),
                UNIQUE (number, shift_id, specimen_id),
                FOREIGN KEY (shift_id, specimen_id)
                    REFERENCES roster_entries(shift_id, specimen_id)
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS result_sources (
                number INTEGER NOT NULL,
                shift_id TEXT NOT NULL,
                specimen_id TEXT NOT NULL,
                head TEXT NOT NULL CHECK (head IN ('left', 'right')),
                exposure_id TEXT NOT NULL,
                PRIMARY KEY (number, head),
                FOREIGN KEY (number, shift_id, specimen_id)
                    REFERENCES issued_results(number, shift_id, specimen_id),
                FOREIGN KEY (exposure_id, shift_id, specimen_id, head)
                    REFERENCES raw_readings(exposure_id, shift_id, specimen_id, head)
            )
        ''')

    def insert(self, connection, shift_id, specimen_id, values, decision, pair, *, after_header):
        cursor = connection.execute('''
            INSERT INTO issued_results (
                shift_id, specimen_id, left_um, right_um, difference_um, accepted
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            shift_id, specimen_id, encode_integer(values.left_um), encode_integer(values.right_um),
            encode_integer(decision.difference_um), int(decision.accepted),
        ))
        number = cursor.lastrowid
        after_header()
        sources = (
            ResultSourceRef('left', pair.left.identity.exposure_id),
            ResultSourceRef('right', pair.right.identity.exposure_id),
        )
        connection.executemany('''
            INSERT INTO result_sources (number, shift_id, specimen_id, head, exposure_id)
            VALUES (?, ?, ?, ?, ?)
        ''', ((number, shift_id, specimen_id, ref.head, ref.exposure_id) for ref in sources))
        return IssuedResult(
            number, shift_id, specimen_id, values.left_um, values.right_um,
            decision.difference_um, decision.accepted, sources,
        )

    def by_number(self, connection, number):
        if type(number) is not int or number < 1:
            raise ValueError('result number must be a positive integer')
        if number > (1 << 63) - 1:
            return None
        row = connection.execute('SELECT * FROM issued_results WHERE number = ?', (number,)).fetchone()
        return None if row is None else self._result(connection, row)

    def by_specimen(self, connection, shift_id, specimen_id):
        row = connection.execute('''
            SELECT * FROM issued_results WHERE shift_id = ? AND specimen_id = ?
        ''', (shift_id, specimen_id)).fetchone()
        return None if row is None else self._result(connection, row)

    def for_shift(self, connection, shift_id):
        rows = connection.execute('SELECT * FROM issued_results WHERE shift_id = ?', (shift_id,))
        return tuple(self._result(connection, row) for row in rows)

    @staticmethod
    def _result(connection, row):
        sources = connection.execute('''
            SELECT head, exposure_id FROM result_sources WHERE number = ? ORDER BY head
        ''', (row['number'],))
        return IssuedResult(
            row['number'], row['shift_id'], row['specimen_id'],
            decode_integer(row['left_um']), decode_integer(row['right_um']),
            decode_integer(row['difference_um']), bool(row['accepted']),
            tuple(ResultSourceRef(source['head'], source['exposure_id']) for source in sources),
        )
