from dataclasses import dataclass

from station.setup.database import decode_integer, encode_integer


@dataclass(frozen=True, slots=True)
class VisitReceipt:
    exposure_id: str
    number: int


@dataclass(frozen=True, slots=True)
class VisitReading:
    exposure_id: str
    visit_id: str | None
    shift_id: str | None
    specimen_id: str | None
    head: str
    open_position: int
    close_position: int
    valid: bool
    raw_code: int
    receipt: VisitReceipt


class VisitRawStore:
    @staticmethod
    def install_schema(connection):
        connection.execute('''
            CREATE TABLE IF NOT EXISTS visit_readings (
                receipt_number INTEGER PRIMARY KEY,
                exposure_id TEXT NOT NULL UNIQUE,
                visit_id TEXT,
                shift_id TEXT,
                specimen_id TEXT,
                head TEXT NOT NULL CHECK (head IN ('left', 'right')),
                open_position INTEGER NOT NULL CHECK (open_position >= 1),
                close_position INTEGER NOT NULL CHECK (close_position >= 1),
                valid INTEGER NOT NULL CHECK (valid IN (0, 1)),
                raw_code TEXT NOT NULL,
                UNIQUE (visit_id, head),
                FOREIGN KEY (visit_id) REFERENCES visits(visit_id)
            )
        ''')

    def insert(self, connection, exposure, raw_code):
        cursor = connection.execute('''
            INSERT INTO visit_readings (
                exposure_id, visit_id, shift_id, specimen_id, head,
                open_position, close_position, valid, raw_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            exposure.exposure_id, exposure.visit_id, exposure.shift_id,
            exposure.specimen_id, exposure.head, exposure.open_position,
            exposure.close_position, int(exposure.valid), encode_integer(raw_code),
        ))
        return VisitReceipt(exposure.exposure_id, cursor.lastrowid)

    def by_exposure(self, connection, exposure_id):
        row = connection.execute(
            'SELECT * FROM visit_readings WHERE exposure_id = ?', (exposure_id,)
        ).fetchone()
        return None if row is None else self._reading(row)

    def for_visit(self, connection, visit_id):
        rows = connection.execute(
            'SELECT * FROM visit_readings WHERE visit_id = ? ORDER BY head', (visit_id,)
        )
        return tuple(self._reading(row) for row in rows)

    @staticmethod
    def _reading(row):
        return VisitReading(
            row['exposure_id'], row['visit_id'], row['shift_id'], row['specimen_id'],
            row['head'], row['open_position'], row['close_position'],
            bool(row['valid']), decode_integer(row['raw_code']),
            VisitReceipt(row['exposure_id'], row['receipt_number']),
        )
