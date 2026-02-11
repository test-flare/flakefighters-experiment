import argparse
import json
import os
import subprocess

from git import Repo

# --- Configuration ---
REPO_PATH = "./core"  # Path where the repo will be cloned
REPO_URL = "https://github.com/home-assistant/core.git"
ITERATIONS = 1000


def main():
    parser = argparse.ArgumentParser(
        prog="reproduce_flakiness",
        description="Attempts to reproduce flaky behaviour for a given test case of the home-assistant git repo.",
    )
    parser.add_argument("-s", "--source-sha", help="Source commit sha.")
    parser.add_argument("-t", "--target-sha", help="Target commit sha.")
    parser.add_argument("-T", "--test-path", help="Name of the test to run.")
    parser.add_argument("-o", "--output", help="Output file path.")
    args = parser.parse_args()

    repo = Repo(REPO_PATH)
    repo.git.fetch()
    repo.git.checkout(args.target_sha)
    repo.remotes.origin.fetch(args.source_sha)
    repo.git.merge("FETCH_HEAD")

    with open(os.path.join(REPO_PATH, "pyproject.toml"), "a") as f:
        f.write(
            """
[tool.pytest.ini_options.pytest_flakefighters.flakefighters.deflaker.DeFlaker]
run_live=false

[tool.pytest.ini_options.pytest_flakefighters.flakefighters.traceback_matching.TracebackMatching]
run_live=false

[tool.pytest.ini_options.pytest_flakefighters.flakefighters.traceback_matching.CosineSimilarity]
run_live=false

[tool.pytest.ini_options.pytest_flakefighters.flakefighters.coverage_independence.CoverageIndependence]
run_live=false
"""
        )

    subprocess.run("./script/setup", check=True, cwd=REPO_PATH)

    successes = 0
    failures = 0
    confirmed = False

    for i in range(1, ITERATIONS + 1):
        if successes and failures:
            confirmed = True
            break
        process = subprocess.run(
            f"pytest {args.test_path} --database-url=sqlite:///{args.output.replace('.json', '.db')}",
            shell=True,
            cwd=REPO_PATH,
            capture_output=True,
            check=False,
        )

        if process.returncode == 0:
            successes += 1
        else:
            failures += 1

    with open(args.output, "w") as f:
        json.dump(
            {
                "source_sha": args.source_sha,
                "target_sha": args.target_sha,
                "flaky_test_candidate": args.test_path,
                "confirmed": confirmed,
                "successes": successes,
                "failures": failures,
            },
            f,
            indent=2,
        )


if __name__ == "__main__":
    main()
