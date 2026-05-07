"""
This module contains code to process the data for the evaluation experiment.
"""

from glob import glob
from pytest_flakefighters.database_management import Database, Run, TestExecution, Test
import os
import json
import re
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

test_name_re = re.compile(r"(tests/[\w\/\.\d_]+::[\w\d_]+)")
RUNS_FILE = "home_assistant_flakes_dev.json"


def get_flakefighter_data(file: str):
    db = Database(f"sqlite:///{os.path.abspath(file)}")
    with Session(db.engine) as session:
        stmt = (
            select(TestExecution)
            .join(TestExecution.test)  # Join to Test
            .join(Test.run)  # Join to Run
            .filter(TestExecution.outcome == "failed")
            .order_by(desc(Run.start_time))
            .limit(1)
        )

        first_failed_exec = session.scalars(stmt).first()

        if first_failed_exec:
            test = first_failed_exec.test

            # Build your datum dictionary
            datum = {f.name: f.flaky for f in test.flakefighter_results}
            datum |= {f.name: f.flaky for f in first_failed_exec.flakefighter_results}
            db.engine.dispose()
            return datum
        db.engine.dispose()
        return {}


def main():
    data = []

    results_files = sorted(glob("outputs-new/**/components/**/*.db", recursive=True))
    runs = pd.read_json(RUNS_FILE)
    runs = runs.explode("failed_tests").reset_index(drop=True).sort_values("run_id")
    expanded_cols = pd.json_normalize(runs["failed_tests"])
    runs = pd.concat([runs.drop("failed_tests", axis=1), expanded_cols], axis=1)

    for file in results_files:
        with open(file.replace(".db", ".json")) as f:
            log = json.load(f)
        print(file, log["target_sha"])
        # run_id = runs.query(
        #     f"(test_id == '{log['test_id']}') & (target_sha == '{log['target_sha']}' | source_sha == '{log['target_sha']}')"
        # )
        # print(Path(file).parts[-2])
        # print(" ", run_id)
        # assert len(run_id) > 0, f"Nothing found for {log['target_sha']}"
        # assert (
        #     len(set(run_id["run_id"])) == 1
        # ), f"Multiple runs found!\n{run_id[['run_id', 'source_sha', 'target_sha', 'test_id']].to_dict()}"
        # [run_id] = list(set(run_id["run_id"]))
        datum = {
            # "run_id": run_id,
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
