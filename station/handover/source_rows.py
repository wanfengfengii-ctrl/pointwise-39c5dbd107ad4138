from dataclasses import dataclass


class EvidenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourceRow:
    exposure_id: str
    shift_id: str
    specimen_id: str
    head: str
    raw_code: int


def read_source_rows(connection, raw_store, references):
    sources = []
    for reference in references:
        reading = raw_store.by_exposure(connection, reference.exposure_id)
        if reading is None:
            raise EvidenceError(f'missing raw source {reference.exposure_id!r}')
        identity = reading.identity
        sources.append(SourceRow(
            identity.exposure_id, identity.shift_id, identity.specimen_id, identity.head,
            reading.raw_code,
        ))
    return tuple(sources)
