from dataclasses import dataclass

from station.bench.exposure import Exposure
from station.bench.recording import RawReply
from station.setup.roster import validate_identifier


@dataclass(frozen=True, slots=True)
class ReadingIdentity:
    exposure_id: str
    shift_id: str
    specimen_id: str
    head: str


def identity_from_exposure(exposure: Exposure) -> ReadingIdentity:
    if exposure.phase != 'closed':
        raise ValueError('cannot accept a reply for an unfinished exposure')
    return ReadingIdentity(exposure.exposure_id, exposure.shift_id, exposure.specimen_id, exposure.head)


def check_reply_identity(reply: RawReply, expected: ReadingIdentity) -> None:
    if type(reply.raw_code) is not int:
        raise ValueError('raw code must be an integer')
    validate_identifier(reply.shift_id, 'shift ID')
    validate_identifier(reply.specimen_id, 'specimen ID')
    observed = ReadingIdentity(reply.exposure_id, reply.shift_id, reply.specimen_id, reply.head)
    if observed != expected:
        raise ValueError(f'reply identity differs from exposure {expected.exposure_id!r}')
