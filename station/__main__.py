import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from station import Station
from station.bench.offline import OfflineBench


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


def main():
    parser = argparse.ArgumentParser(description='Run a fixed-clamp shift and collect results offline.')
    parser.parse_args()
    with TemporaryDirectory(prefix='thickness-demo-') as directory:
        path = Path(directory) / 'station.sqlite'
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


if __name__ == '__main__':
    main()
