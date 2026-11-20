import sqlite3
from contextlib import contextmanager


class InjectedFailure(RuntimeError):
    pass


def encode_integer(value: int) -> str:
    if type(value) is not int:
        raise ValueError('expected an integer')
    return hex(value)


def decode_integer(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError('stored integer must be text')
    decoded = int(value, 16)
    if encode_integer(decoded) != value:
        raise ValueError('invalid stored integer encoding')
    return decoded


class StationDatabase:
    def __init__(self, path, *, checkpoint=None):
        self._connection = sqlite3.connect(path, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute('PRAGMA foreign_keys = ON')
        self._checkpoint = checkpoint

    def initialize(self, *installers):
        with self.write('initialize') as connection:
            for install in installers:
                install(connection)

    def checkpoint(self, point):
        if self._checkpoint is not None:
            self._checkpoint(point)

    @contextmanager
    def read(self):
        with self._transaction('BEGIN') as connection:
            yield connection

    @contextmanager
    def write(self, operation):
        with self._transaction('BEGIN IMMEDIATE') as connection:
            yield connection
            self.checkpoint(f'{operation}.before_commit')

    @contextmanager
    def _transaction(self, begin):
        connection = self._connection
        connection.execute(begin)
        try:
            yield connection
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    def close(self):
        self._connection.close()
