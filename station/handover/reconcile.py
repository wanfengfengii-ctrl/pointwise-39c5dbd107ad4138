from station.bench.exposure import HEADS
from station.handover.source_rows import EvidenceError


def verify_result_sources(result, sources):
    if tuple(reference.head for reference in result.sources) != HEADS or len(sources) != len(HEADS):
        raise EvidenceError(f'result {result.number} requires two ordered head references')
    for reference, source in zip(result.sources, sources, strict=True):
        if (source.shift_id, source.specimen_id, source.head, source.exposure_id) != (
            result.shift_id, result.specimen_id, reference.head, reference.exposure_id
        ):
            raise EvidenceError(f'raw source {source.exposure_id!r} does not match result {result.number}')
