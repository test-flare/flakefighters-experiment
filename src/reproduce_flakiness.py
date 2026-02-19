import argparse
import json
import os
import subprocess

from git import Repo

from home_assistant_pr_scraper import parse_test_failures

# --- Configuration ---
REPO_PATH = "./core"  # Path where the repo will be cloned
REPO_URL = "https://github.com/home-assistant/core.git"
ITERATIONS = 100


def search_for_flakiness(test_path, db_url):
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
    successes = 0
    failures = 0
    confirmed = False

    test_to_run = test_path.split("::")[0]

    for _ in range(ITERATIONS):
        if successes and failures:
            confirmed = True
            break
        print(f"pytest {test_to_run} --database-url={db_url}")
        process = subprocess.run(
            f"pytest {test_to_run} --database-url={db_url}",
            shell=True,
            cwd=REPO_PATH,
            capture_output=True,
            check=False,
        )
        failed_tests = parse_test_failures(process.stdout.decode("utf-8"))
        print("FAILED TESTS", failed_tests)

        if process.returncode == 0:
            successes += 1
            test_to_run = test_path
        else:
            failures += 1
    return {"successes": successes, "failures": failures, "confirmed": confirmed}


def main():
    parser = argparse.ArgumentParser(
        prog="reproduce_flakiness",
        description="Attempts to reproduce flaky behaviour for a given test case of the home-assistant git repo.",
    )
    parser.add_argument("-s", "--source-sha", help="Source commit sha.")
    parser.add_argument("-t", "--target-sha", help="Target commit sha.")
    parser.add_argument("-S", "--sample-shas", nargs="+", help="List of historic commits to run the tests on.")
    parser.add_argument("-T", "--test-path", help="Name of the test to run.")
    parser.add_argument("-o", "--output", help="Output file path.")
    args = parser.parse_args()

    repo = Repo(REPO_PATH)
    repo.git.checkout("--", "pyproject.toml")
    repo.git.fetch()

    flakiness = {}
    for sha in args.sample_shas:
        repo.git.checkout(sha)
        flakiness[sha] = search_for_flakiness(args.test_path, f"sqlite:///{args.output.replace('.json', '.db')}")
        repo.git.checkout("--", "pyproject.toml")

    repo.git.checkout(args.target_sha)
    repo.remotes.origin.fetch(args.source_sha)
    repo.git.merge("FETCH_HEAD")

    subprocess.run("./script/setup", check=True, cwd=REPO_PATH)

    flakiness["PR"] = search_for_flakiness(args.test_path, f"sqlite:///{args.output.replace('.json', '.db')}")
    repo.git.checkout("--", "pyproject.toml")

    with open(args.output, "w") as f:
        json.dump(
            {
                "source_sha": args.source_sha,
                "target_sha": args.target_sha,
                "flaky_test_candidate": args.test_path,
                "flakiness": flakiness,
            },
            f,
            indent=2,
        )


if __name__ == "__main__":
    main()
