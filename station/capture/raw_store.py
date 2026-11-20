from dataclasses import dataclass

from station.capture.identity import ReadingIdentity
from station.setup.database import decode_integer, encode_integer


@dataclass(frozen=True, slots=True)
class AdmissionReceipt:
    exposure_id: str
    number: int


@dataclass(frozen=True, slots=True)
class RawReading:
    identity: ReadingIdentity
    raw_code: int
    receipt: AdmissionReceipt


class RawStore:
    @staticmethod
    def install_schema(connection):
        connection.execute('''
            CREATE TABLE IF NOT EXISTS raw_readings (
                receipt_number INTEGER PRIMARY KEY,
                exposure_id TEXT NOT NULL UNIQUE,
                shift_id TEXT NOT NULL,
                specimen_id TEXT NOT NULL,
                head TEXT NOT NULL CHECK (head IN ('left', 'right')),
                raw_code TEXT NOT NULL,
                UNIQUE (shift_id, specimen_id, head),
                UNIQUE (exposure_id, shift_id, specimen_id, head),
                FOREIGN KEY (shift_id, specimen_id)
                    REFERENCES roster_entries(shift_id, specimen_id)
            )
        ''')

    def insert(self, connection, identity: ReadingIdentity, raw_code: int):
        cursor = connection.execute('''
            INSERT INTO raw_readings (exposure_id, shift_id, specimen_id, head, raw_code)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            identity.exposure_id, identity.shift_id, identity.specimen_id,
            identity.head, encode_integer(raw_code),
        ))
        return RawReading(identity, raw_code, AdmissionReceipt(identity.exposure_id, cursor.lastrowid))

    def by_exposure(self, connection, exposure_id):
        row = connection.execute(
            'SELECT * FROM raw_readings WHERE exposure_id = ?', (exposure_id,)
        ).fetchone()
        return None if row is None else self._reading(row)

    def for_specimen(self, connection, shift_id, specimen_id):
        rows = connection.execute('''
            SELECT * FROM raw_readings
            WHERE shift_id = ? AND specimen_id = ? ORDER BY head
        ''', (shift_id, specimen_id))
        return tuple(self._reading(row) for row in rows)

    @staticmethod
    def _reading(row):
        exposure_id = row['exposure_id']
        identity = ReadingIdentity(exposure_id, row['shift_id'], row['specimen_id'], row['head'])
        receipt = AdmissionReceipt(exposure_id, row['receipt_number'])
        return RawReading(identity, decode_integer(row['raw_code']), receipt)
