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


def get_flakefighter_data(file: str):
    runs = Database(f"sqlite:///{os.path.abspath(file)}").load_runs()
    for run in runs:
        for test in run.tests:
            datum = {f.name: f.flaky for f in test.flakefighter_results}
            for execution in test.executions:
                # Only want to log the first failing execution as the "result"
                if execution.outcome == "failed":
                    datum |= {f.name: f.flaky for f in execution.flakefighter_results}
                    return datum
    return {}


def main():
    data = []

    results_files = sorted(glob("outputs/tests/components/**/*.db", recursive=True))
    for file in results_files:
        with open(file.replace(".db", ".json")) as f:
            log = json.load(f)
        datum = {
            "test": Path(file).parts[-2],
            "source_sha": log["source_sha"],
            "target_sha": log["target_sha"],
            "confirmed": log["flakiness"]["confirmed"],
            "successes": log["flakiness"]["successes"],
            "failures": log["flakiness"]["failures"],
        } | get_flakefighter_data(file)
        data.append(datum)

    data = pd.DataFrame(data)
    data.to_csv("results.csv")


if __name__ == "__main__":
    main()
