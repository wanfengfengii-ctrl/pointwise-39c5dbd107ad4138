import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from station import Station
from station.bench.offline import OfflineBench
from station.quality.eligibility import HeadCoverage


SAMPLES = (
    ('n7', 'P', (3, 7), (10, 12, 2, True), ('day-000001', 'day-000002')),
    ('n7.affine_signed', 'Q', (4, 6), (13, 10, -3, False), ('day-000003', 'day-000004')),
)


def capture_specimen(bench, capture, specimen, codes):
    bench.emit('mount', shift_id='day', specimen_id=specimen)
    exposures = {head: bench.request_measurement(head) for head in ('left', 'right')}
    for (head, exposure_id), code in zip(exposures.items(), codes, strict=True):
        bench.emit('open', exposure_id=exposure_id, head=head)
        bench.emit('close', exposure_id=exposure_id, head=head)
        bench.record(exposure_id, code)
    bench.emit('unmount')
    for head in ('right', 'left'):
        capture.admit(bench.deliver_reply(exposures[head]))
    if any(bench.adapter.exposure_edges(exposure_id) for exposure_id in exposures.values()):
        raise AssertionError('device did not reclaim exposure edges')


def decision_row(result):
    return [result.left_um, result.right_um, result.difference_um, result.accepted]


def visit_demo(path):
    """Same-seat reentry, out-of-order replies, empty-seat open and reopen."""
    with Station(path) as station:
        station.shifts.open('A', ('P',), (1, 7), (2, -2), 2)
        bench = OfflineBench(station.shifts, namespace='visit-demo', visit_mode=True)
        capture = station.attach(bench)
        # First stay: a left exposure that spans an unmount becomes invalid.
        first = bench.emit('mount', shift_id='A', specimen_id='P')
        bench.emit('open', exposure_id='span-L', head='left')
        bench.emit('unmount')
        # An open while the seat is empty belongs to no visit.
        bench.emit('open', exposure_id='empty-L', head='left')
        second = bench.emit('mount', shift_id='A', specimen_id='P')
        bench.emit('close', exposure_id='span-L', head='left')
        bench.emit('close', exposure_id='empty-L', head='left')
        capture.admit(bench.record('span-L', 3))
        capture.admit(bench.record('empty-L', 9))
        # Second stay receives both valid heads; replies arrive out of order.
        right = 'stay-R'
        left = 'stay-L'
        bench.emit('open', exposure_id=right, head='right')
        bench.emit('close', exposure_id=right, head='right')
        bench.emit('open', exposure_id=left, head='left')
        bench.emit('close', exposure_id=left, head='left')
        right_reply = bench.record(right, 7)
        left_reply = bench.record(left, 4)
        capture.admit(right_reply)
        first_coverage = station.quality.issue_visit(first)
        second_coverage = station.quality.issue_visit(second)
        capture.admit(left_reply)
        issued = station.quality.issue_visit(second)
        bench.close()
    with Station(path) as station:
        collected = station.lookup.collect_visit(issued.number)
        if collected != issued:
            raise AssertionError('reopened visit result differs from the issued result')
        source_rows = [[row.visit_id, row.exposure_id, row.head,
                        row.open_position, row.close_position, row.raw_code]
                       for row in collected.sources]
        payload = {
            'case_id': 'visits.reentry',
            'visits': [first, second],
            'coverage': {
                'interrupted_first': [first_coverage.left, first_coverage.right],
                'second_before_left': [second_coverage.left, second_coverage.right],
            },
            'expected_coverage': {
                'interrupted_first': ['invalid', 'missing'],
                'second_before_left': ['missing', 'ready'],
            },
            'empty_seat_open_admitted_without_visit': True,
            'expected': [11, 12, 1, True],
            'actual': decision_row(collected),
            'expected_sources': [
                [second, left, 'left', 10, 11, 4],
                [second, right, 'right', 8, 9, 7],
            ],
            'sources': source_rows,
            'oracle': 'Visit-scoped head validity, frozen shift calibration and edge positions.',
        }
        if (payload['coverage'] != payload['expected_coverage']
                or payload['actual'] != payload['expected']
                or source_rows != payload['expected_sources']):
            raise AssertionError('visit demo observations differ from expectations')
        print('POINTWISE_SCENARIO ' + json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description='Run a fixed-clamp shift and collect results offline.')
    parser.parse_args()
    with TemporaryDirectory(prefix='thickness-demo-') as directory:
        root = Path(directory)
        path = root / 'station.sqlite'
        with Station(path) as station:
            station.shifts.open('day', ('P', 'Q', 'R'), (3, 1), (2, -2), 2)
            bench = OfflineBench(station.shifts, namespace='day')
            capture = station.attach(bench)
            issued = {}
            try:
                for _, specimen, codes, _, _ in SAMPLES:
                    capture_specimen(bench, capture, specimen, codes)
                    issued[specimen] = station.quality.issue('day', specimen)
            finally:
                bench.close()
        with Station(path) as station:
            sheet = station.handover.collect('day')
            if tuple(item.result.specimen_id for item in sheet.items) != ('P', 'Q'):
                raise AssertionError('handover differs from the expected roster projection')
            for case_id, specimen, codes, expected_values, expected_exposures in SAMPLES:
                result = issued[specimen]
                collected = station.lookup.collect(result.number)
                expected = list(expected_values)
                actual = decision_row(result)
                downstream_expected = {
                    'values': expected,
                    'sources': [[head, exposure, code] for head, exposure, code in zip(
                        ('left', 'right'), expected_exposures, codes, strict=True
                    )],
                }
                downstream_actual = {
                    'values': decision_row(collected.result),
                    'sources': [[row.head, row.exposure_id, row.raw_code] for row in collected.sources],
                }
                if actual != expected or downstream_actual != downstream_expected:
                    raise AssertionError(f'demo values or sources differ for {specimen!r}')
                print('POINTWISE_SCENARIO ' + json.dumps({
                    'case_id': case_id,
                    'input': {
                        'shift': 'day', 'specimen': specimen, 'left': [3, 1], 'right': [2, -2],
                        'tolerance_um': 2, 'raw_codes_left_right': codes,
                        'reply_order': ['right', 'left'],
                    },
                    'expected': expected,
                    'actual': actual,
                    'downstream_expected': downstream_expected,
                    'downstream_actual': downstream_actual,
                    'code_paths': [
                        'station/bench/events.py', 'station/capture/admit.py',
                        'station/quality/convert.py', 'station/quality/classify.py',
                        'station/quality/issue.py', 'station/handover/lookup.py',
                    ],
                    'oracle': 'Manually calculated affine values, signed difference, tolerance and exposure order.',
                }, sort_keys=True))
        visit_demo(root / 'visits.sqlite')


if __name__ == '__main__':
    main()
