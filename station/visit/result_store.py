from dataclasses import dataclass

from station.setup.database import decode_integer, encode_integer


@dataclass(frozen=True, slots=True)
class VisitSource:
    visit_id: str
    exposure_id: str
    head: str
    open_position: int
    close_position: int
    raw_code: int


@dataclass(frozen=True, slots=True)
class VisitResult:
    number: int
    visit_id: str
    shift_id: str
    specimen_id: str
    left_um: int
    right_um: int
    difference_um: int
    accepted: bool
    sources: tuple[VisitSource, VisitSource]


class VisitResultStore:
    @staticmethod
    def install_schema(connection):
        connection.execute('''
            CREATE TABLE IF NOT EXISTS visit_results (
                number INTEGER PRIMARY KEY,
                visit_id TEXT NOT NULL UNIQUE REFERENCES visits(visit_id),
                shift_id TEXT NOT NULL,
                specimen_id TEXT NOT NULL,
                left_um TEXT NOT NULL,
                right_um TEXT NOT NULL,
                difference_um TEXT NOT NULL,
                accepted INTEGER NOT NULL CHECK (accepted IN (0, 1))
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS visit_result_sources (
                number INTEGER NOT NULL,
                visit_id TEXT NOT NULL,
                head TEXT NOT NULL CHECK (head IN ('left', 'right')),
                exposure_id TEXT NOT NULL,
                open_position INTEGER NOT NULL,
                close_position INTEGER NOT NULL,
                raw_code TEXT NOT NULL,
                PRIMARY KEY (number, head),
                FOREIGN KEY (number) REFERENCES visit_results(number),
                FOREIGN KEY (exposure_id) REFERENCES visit_readings(exposure_id)
            )
        ''')

    def insert(self, connection, visit, values, decision, pair, *, after_header):
        visit_id, shift_id, specimen_id = visit
        cursor = connection.execute('''
            INSERT INTO visit_results (
                visit_id, shift_id, specimen_id, left_um, right_um,
                difference_um, accepted
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            visit_id, shift_id, specimen_id,
            encode_integer(values.left_um), encode_integer(values.right_um),
            encode_integer(decision.difference_um), int(decision.accepted),
        ))
        number = cursor.lastrowid
        after_header()
        sources = tuple(
            VisitSource(
                visit_id, reading.exposure_id, reading.head,
                reading.open_position, reading.close_position, reading.raw_code,
            )
            for reading in (pair.left, pair.right)
        )
        connection.executemany('''
            INSERT INTO visit_result_sources (
                number, visit_id, head, exposure_id,
                open_position, close_position, raw_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', ((
            number, source.visit_id, source.head, source.exposure_id,
            source.open_position, source.close_position, encode_integer(source.raw_code),
        ) for source in sources))
        return VisitResult(
            number, visit_id, shift_id, specimen_id, values.left_um, values.right_um,
            decision.difference_um, decision.accepted, sources,
        )

    def by_visit(self, connection, visit_id):
        row = connection.execute(
            'SELECT * FROM visit_results WHERE visit_id = ?', (visit_id,)
        ).fetchone()
        return None if row is None else self._result(connection, row)

    def by_number(self, connection, number):
        if type(number) is not int or number < 1:
            raise ValueError('result number must be a positive integer')
        if number > (1 << 63) - 1:
            return None
        row = connection.execute(
            'SELECT * FROM visit_results WHERE number = ?', (number,)
        ).fetchone()
        return None if row is None else self._result(connection, row)

    @staticmethod
    def _result(connection, row):
        sources = connection.execute('''
            SELECT visit_id, exposure_id, head, open_position, close_position, raw_code
            FROM visit_result_sources WHERE number = ? ORDER BY head
        ''', (row['number'],))
        return VisitResult(
            row['number'], row['visit_id'], row['shift_id'], row['specimen_id'],
            decode_integer(row['left_um']), decode_integer(row['right_um']),
            decode_integer(row['difference_um']), bool(row['accepted']),
            tuple(VisitSource(
                source['visit_id'], source['exposure_id'], source['head'],
                source['open_position'], source['close_position'],
                decode_integer(source['raw_code']),
            ) for source in sources),
        )
