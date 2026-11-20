class ConfirmationQueue:
    @staticmethod
    def install_schema(connection):
        connection.execute('''
            CREATE TABLE IF NOT EXISTS confirmations (
                exposure_id TEXT PRIMARY KEY NOT NULL REFERENCES raw_readings(exposure_id),
                confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1))
            )
        ''')
        connection.execute('''
            CREATE INDEX IF NOT EXISTS pending_confirmations
            ON confirmations(exposure_id) WHERE confirmed = 0
        ''')

    def enqueue(self, connection, exposure_id):
        connection.execute('INSERT INTO confirmations (exposure_id) VALUES (?)', (exposure_id,))

    def pending(self, connection, exposure_id=None):
        if exposure_id is None:
            rows = connection.execute('''
                SELECT exposure_id FROM confirmations WHERE confirmed = 0 ORDER BY exposure_id
            ''')
        else:
            rows = connection.execute('''
                SELECT exposure_id FROM confirmations WHERE exposure_id = ? AND confirmed = 0
            ''', (exposure_id,))
        return tuple(row['exposure_id'] for row in rows)

    def mark_confirmed(self, connection, exposure_id):
        connection.execute('''
            UPDATE confirmations SET confirmed = 1 WHERE exposure_id = ? AND confirmed = 0
        ''', (exposure_id,))
