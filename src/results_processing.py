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
from tqdm import tqdm

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

    results_files = sorted(glob("outputs/**/components/**/*.db", recursive=True))
    runs = pd.read_json(RUNS_FILE)
    runs = runs.explode("failed_tests").reset_index(drop=True).sort_values("run_id")
    expanded_cols = pd.json_normalize(runs["failed_tests"])
    runs = pd.concat([runs.drop("failed_tests", axis=1), expanded_cols], axis=1)

    for file in tqdm(results_files):
        with open(file.replace(".db", ".json")) as f:
            log = json.load(f)
        datum = {
            # "run_id": run_id,
            "test_id": Path(file).parts[-2],
            "source_sha": log["source_sha"],
            "target_sha": log["target_sha"],
            "confirmed": log["flakiness"]["confirmed"],
            "successes": log["flakiness"]["successes"],
            "failures": log["flakiness"]["failures"],
        } | get_flakefighter_data(file)
        data.append(datum)

    flakefighters = {
        "CoverageIndependence": "Coverage Matching",
        "DiffCov": "Differential Coverage",
        "TracebackMatching": "Failure Log Matching",
        "CosineSimilarity": "Cosine Similarity",
    }
    data = pd.DataFrame(data)
    data["Combined"] = data[list(flakefighters)].any(axis=1)
    data = data.loc[~pd.isnull(data["source_sha"])]
    data.to_csv("results.csv")

    eval_table = []

    data = data.query("failures > 0")

    for flakefighter in list(flakefighters) + ["Combined"]:
        true_positives = (data["confirmed"] & (data[flakefighter].astype("boolean"))).sum()
        false_positives = (~data["confirmed"] & (data[flakefighter].astype("boolean"))).sum()
        true_negatives = ((~data["confirmed"]) & (~data[flakefighter].astype("boolean"))).sum()
        false_negatives = (data["confirmed"] & (~data[flakefighter].astype("boolean"))).sum()

        eval_table.append(
            {
                "Flakefighter": flakefighters.get(flakefighter, "Combined"),
                "True Positives": true_positives,
                "False Positives": false_positives,
                "True Negatives": true_negatives,
                "False Negatives": false_negatives,
            }
        )

    eval_table = pd.DataFrame(eval_table).round(3)
    print(eval_table)
    eval_table.sort_values(["True Positives", "False Positives"], ascending=False).to_latex(
        "results.tex", index=False, float_format="{:.3f}".format
    )

    print()
    print(len(set(data["test_id"])), "tests in total")
    for source in [True, False]:
        if source:
            pr_code = data.loc[pd.isnull(data["source_sha"])]
        else:
            pr_code = data.loc[~pd.isnull(data["source_sha"])]
        all_failed = len(pr_code.query("successes == 0"))
        all_passed = len(pr_code.query("failures == 0"))
        flaky = len(pr_code.query("(successes > 0) & (failures > 0)"))
        print(
            "PR", "source" if source else "target", all_passed, "only passed", all_failed, "only failed", flaky, "flaky"
        )


if __name__ == "__main__":
    main()
