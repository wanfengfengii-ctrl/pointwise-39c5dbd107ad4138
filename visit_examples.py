import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from station import Station
from station.bench.offline import FaultSchedule, OfflineBench
from station.setup.database import InjectedFailure


def reject(error, operation, *args):
    try:
        operation(*args)
    except error:
        return
    raise AssertionError(f'expected {error.__name__}')


def edge(bench, kind, exposure, head):
    bench.emit(kind, exposure_id=exposure, head=head)


def coverage(station, visit):
    state = station.quality.issue_visit(visit)
    return state.left, state.right


def late_replies(path):
    faults = FaultSchedule()
    with Station(path, checkpoint=faults) as station:
        station.shifts.open('A', ('P',), (1, 7), (2, -2), 2)
        bench = OfflineBench(station.shifts, namespace='late', visit_mode=True)
        capture = station.attach(bench)
        first = bench.emit('mount', shift_id='A', specimen_id='P')
        edge(bench, 'open', 'late-L1', 'left')
        edge(bench, 'close', 'late-L1', 'left')
        original = bench.record('late-L1', 3)
        bench.emit('unmount')
        second = bench.emit('mount', shift_id='A', specimen_id='P')
        assert first != second
        edge(bench, 'open', 'late-R2', 'right')
        edge(bench, 'close', 'late-R2', 'right')
        right = bench.record('late-R2', 7)
        capture.admit(right)
        reject(KeyError, bench.deliver_reply, 'late-R2')
        faults.arm('admit.before_commit')
        reject(InjectedFailure, capture.admit, original)
        assert bench.confirmation.attempts('late-L1') == 0
        assert coverage(station, first) == ('missing', 'missing')
        receipt = capture.admit(original)
        reject(KeyError, bench.deliver_reply, 'late-L1')
        assert capture.admit(original) == receipt
        reject(ValueError, capture.admit, replace(original, raw_code=4))
        prior = [coverage(station, first), coverage(station, second)]
        assert prior == [('ready', 'missing'), ('missing', 'ready')]
        edge(bench, 'open', 'late-L2', 'left')
        edge(bench, 'close', 'late-L2', 'left')
        capture.admit(bench.record('late-L2', 4))
        faults.arm('issue.before_commit')
        reject(InjectedFailure, station.quality.issue_visit, second)
        issued = station.quality.issue_visit(second)
        assert station.quality.issue_visit(second) == issued
        bench.close()
    with Station(path) as reopened:
        got = reopened.lookup.collect_visit(issued.number)
        assert got == issued
        assert (got.visit_id, got.shift_id, got.specimen_id) == (second, 'A', 'P')
        actual = (got.left_um, got.right_um, got.difference_um, got.accepted)
        sources = [(row.visit_id, row.exposure_id, row.head, row.open_position,
                    row.close_position, row.raw_code) for row in got.sources]
        assert actual == (11, 12, 1, True)
        assert sources == [(second, 'late-L2', 'left', 8, 9, 4),
                           (second, 'late-R2', 'right', 6, 7, 7)]
        return {'coverage_before_left2': prior, 'number': got.number,
                'values': actual, 'sources': sources}


def interruption(path, interrupted):
    with Station(path) as station:
        station.shifts.open('A', ('P',), (1, 7), (2, -2), 2)
        bench = OfflineBench(station.shifts, namespace='span', visit_mode=True)
        capture = station.attach(bench)
        first = bench.emit('mount', shift_id='A', specimen_id='P')
        edge(bench, 'open', 'span-L', 'left')
        if interrupted:
            bench.emit('unmount')
            second = bench.emit('mount', shift_id='A', specimen_id='P')
        else:
            edge(bench, 'open', 'span-R', 'right')
            edge(bench, 'close', 'span-R', 'right')
        edge(bench, 'close', 'span-L', 'left')
        capture.admit(bench.record('span-L', 3))
        reject(KeyError, bench.deliver_reply, 'span-L')
        actual = coverage(station, first)
        if interrupted:
            assert actual == ('invalid', 'missing')
            assert coverage(station, second) == ('missing', 'missing')
        else:
            assert actual == ('ready', 'missing')
        bench.close()
        return actual


def main():
    with TemporaryDirectory(prefix='thickness-visits-') as directory:
        root = Path(directory)
        outcome = {
            'late_replies': late_replies(root / 'late.sqlite'),
            'interrupted': interruption(root / 'interrupted.sqlite', True),
            'continuous': interruption(root / 'continuous.sqlite', False),
        }
    print('POINTWISE_SCENARIO ' + json.dumps(outcome, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
