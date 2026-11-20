from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawReply:
    exposure_id: str
    shift_id: str
    specimen_id: str
    head: str
    raw_code: int


class ReplyBuffer:
    def __init__(self, exposures):
        self._exposures = exposures
        self._replies: dict[str, RawReply] = {}

    def record(self, exposure_id, raw_code):
        if type(raw_code) is not int:
            raise ValueError('raw code must be an integer')
        exposure = self._exposures.find(exposure_id)
        if exposure is None:
            raise KeyError(exposure_id)
        if exposure.phase != 'closed':
            raise ValueError('exposure has not finished')
        previous = self._replies.get(exposure_id)
        if previous is not None:
            if previous.raw_code != raw_code:
                raise ValueError('device reply already has a different raw code')
            return previous
        reply = RawReply(
            exposure.exposure_id, exposure.shift_id, exposure.specimen_id, exposure.head, raw_code
        )
        self._replies[exposure_id] = reply
        return reply

    def get(self, exposure_id):
        return self._replies[exposure_id]

    def release(self, exposure_id):
        self._replies.pop(exposure_id, None)
