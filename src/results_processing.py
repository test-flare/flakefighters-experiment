"""
This module contains code to process the data for the evaluation experiment.
"""

from glob import glob
from pytest_flakefighters.database_management import Database
import os
import json
import re
import pandas as pd
from pathlib import Path

test_name_re = re.compile(r"(tests/[\w\/\.\d_]+::[\w\d_]+)")


def main():
    data = []
    confirmed = 0
    total = 0
    only_passed = 0
    only_failed = 0
    for file in sorted(glob("outputs/tests/components/**/*.db", recursive=True)):
        with open(file.replace(".db", ".json")) as f:
            log = json.load(f)
        confirmed += log["flakiness"]["confirmed"]
        total += 1
        runs = Database(f"sqlite:///{os.path.abspath(file)}").load_runs()
        only_passed += all(e.outcome == "passed" for run in runs for test in run.tests for e in test.executions)
        only_failed += all(e.outcome == "failed" for run in runs for test in run.tests for e in test.executions)
        for run in runs:
            for test in run.tests:
                datum = {"test": test.name, "commit": Path(file).stem}
                for f in test.flakefighter_results:
                    datum[f.name] = f.flaky
                if test_name_re.search(file).group(1) == test_name_re.search(test.name).group(1):
                    for execution in test.executions:
                        x_datum = (
                            dict(datum)
                            | {"outcome": execution.outcome, "reproduced": log["flakiness"]["confirmed"]}
                            | {f.name: f.flaky for f in execution.flakefighter_results}
                        )
                        data.append(x_datum)

    data = pd.DataFrame(data)
    data.to_csv("results.csv")
    print(data)
    print(f"confirmed {confirmed}/{total}")
    print(f"{only_passed} only passed")
    print(f"{only_failed} only failed")


if __name__ == "__main__":
    main()
