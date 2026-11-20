class SourceConfirmation:
    def __init__(self, replies, exposures, release_edges, *, checkpoint=None):
        self._replies = replies
        self._exposures = exposures
        self._release_edges = release_edges
        self._checkpoint = checkpoint
        self._confirmed: set[str] = set()
        self._attempts: dict[str, int] = {}

    def confirm(self, exposure_id):
        already_confirmed = self.is_confirmed(exposure_id)
        if not already_confirmed:
            self._replies.get(exposure_id)
        self._attempts[exposure_id] = self.attempts(exposure_id) + 1
        if already_confirmed:
            return
        self._visit_checkpoint('source.before_confirm')
        self._replies.release(exposure_id)
        self._exposures.release_details(exposure_id)
        self._release_edges(exposure_id)
        self._confirmed.add(exposure_id)
        self._visit_checkpoint('source.after_reclaim')

    def is_confirmed(self, exposure_id):
        return exposure_id in self._confirmed

    def attempts(self, exposure_id):
        return self._attempts.get(exposure_id, 0)

    def _visit_checkpoint(self, point):
        if self._checkpoint is not None:
            self._checkpoint(point)
