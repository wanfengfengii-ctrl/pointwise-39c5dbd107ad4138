from station.setup.roster import validate_identifier


class VisitRegistry:
    """Persisted visit ledger in the station database.

    Visit numbers are minted by the bench's device ledger; the registry only
    durably records each mount and answers lookups after a source restart.
    """

    def __init__(self, database):
        self._database = database

    @staticmethod
    def install_schema(connection):
        connection.execute('''
            CREATE TABLE IF NOT EXISTS visits (
                visit_id TEXT PRIMARY KEY NOT NULL,
                shift_id TEXT NOT NULL,
                specimen_id TEXT NOT NULL,
                FOREIGN KEY (shift_id, specimen_id)
                    REFERENCES roster_entries(shift_id, specimen_id)
            )
        ''')

    def register(self, visit_id, shift_id, specimen_id):
        validate_identifier(visit_id, 'visit ID')
        validate_identifier(shift_id, 'shift ID')
        validate_identifier(specimen_id, 'specimen ID')
        with self._database.write('visit_mount') as connection:
            connection.execute('''
                INSERT INTO visits (visit_id, shift_id, specimen_id)
                VALUES (?, ?, ?)
            ''', (visit_id, shift_id, specimen_id))
        return visit_id

    def get(self, connection, visit_id):
        validate_identifier(visit_id, 'visit ID')
        row = connection.execute(
            'SELECT visit_id, shift_id, specimen_id FROM visits WHERE visit_id = ?',
            (visit_id,),
        ).fetchone()
        if row is None:
            raise KeyError(visit_id)
        return row
