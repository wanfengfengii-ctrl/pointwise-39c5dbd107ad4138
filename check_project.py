"""Run this project's full unittest suite and visit joint verification."""
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_unittest_suite():
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    if suite.countTestCases():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print('No tests discovered in tests/', file=sys.stderr)
        result = unittest.TestResult()
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    successful = result.testsRun > 0 and result.wasSuccessful()
    print(f'TEST SUMMARY total={result.testsRun} failures={len(result.failures)} '
          f'errors={len(result.errors)} skipped={len(result.skipped)} '
          f'expected_failures={len(result.expectedFailures)} '
          f'unexpected_successes={len(result.unexpectedSuccesses)} '
          f'result={"PASS" if successful else "FAIL"}')
    return successful, result.testsRun


def run_visit_verification():
    print('VISIT VERIFICATION python3 -B visit_examples.py')
    completed = subprocess.run(
        [sys.executable, '-B', str(ROOT / 'visit_examples.py')],
        cwd=ROOT,
    )
    successful = completed.returncode == 0
    print(f'VISIT SUMMARY result={"PASS" if successful else "FAIL"} '
          f'exit_code={completed.returncode}')
    return successful


def main():
    suite_ok, _ = run_unittest_suite()
    visits_ok = run_visit_verification()
    return 0 if suite_ok and visits_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
