import argparse
import json
import os
import subprocess
import re

from glob import glob

from git import Repo


# --- Configuration ---
REPO_PATH = "./core"  # Path where the repo will be cloned
REPO_URL = "https://github.com/home-assistant/core.git"
ITERATIONS = 2

replacements = {r"mypy\-dev==\d+\.\d+\.\w+": "mypy-dev", r"aioasuswrt==1\.5\.1": "aioasuswrt==1.5.2"}


def parse_test_failures(content):
    failed_tests = []
    # Pytest failure pattern in logs: FAILED path/to/test.py::test_name
    pytest_fail_regex = re.compile(r"(FAILED|ERROR|FLAKY)\s+([\w\/\.\d_]+::[\w\d_]+)")
    matches = pytest_fail_regex.findall(content)
    for m in matches:
        if m not in failed_tests:
            failed_tests.append(m[-1])
    return failed_tests


def search_for_flakiness(test_path, db_url):
    for fname in glob(os.path.join(REPO_PATH, "*requirements*.txt"), recursive=True) + [
        os.path.join(REPO_PATH, "homeassistant/package_constraints.txt")
    ]:
        with open(fname) as f:
            packages = f.readlines()
        for old, new in replacements.items():
            packages = [re.sub(old, new, p) for p in packages]
        with open(fname, "w") as f:
            f.write("\n".join(packages))

    result = subprocess.run(
        "./script/setup",
        check=False,
        shell=True,
        cwd=REPO_PATH,
        capture_output=True,
    )
    if result.returncode != 0:
        return {"successes": None, "failures": None, "confirmed": None, "error": result.stderr.decode("utf-8")}
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

        # if process.returncode == 0:
        if test_path not in failed_tests:
            successes += 1
            test_to_run = test_path
        else:
            failures += 1

    assert os.path.exists(db_url), f"No database at {db_url}"
    return {"successes": successes, "failures": failures, "confirmed": confirmed}


def check_sha(repo, target_sha, test_path, db_url, source_sha=None):
    repo.git.checkout(target_sha)
    if source_sha is not None:
        repo.remotes.origin.fetch(source_sha)
        repo.git.merge("FETCH_HEAD")

    flakiness = search_for_flakiness(test_path, db_url)
    repo.git.reset("--hard")
    return flakiness


def main():
    parser = argparse.ArgumentParser(
        prog="reproduce_flakiness",
        description="Attempts to reproduce flaky behaviour for a given test case of the home-assistant git repo.",
    )
    parser.add_argument("-s", "--source-sha", help="Source commit sha.")
    parser.add_argument("-t", "--target-sha", help="Target commit sha.")
    parser.add_argument("-T", "--test-path", help="Name of the test to run.")
    parser.add_argument("-S", "--sample-shas", nargs="+", help="List of historic commits to run the tests on.")
    parser.add_argument("-o", "--output", help="Output file path.")
    args = parser.parse_args()

    db_url = f"sqlite:///{args.output.replace('.json', '.db')}"

    repo = Repo(REPO_PATH)
    repo.git.reset("--hard")
    repo.git.fetch()

    flakiness = {}
    for sha in args.sample_shas:
        flakiness[sha] = check_sha(repo, sha, args.test_path, db_url)
    flakiness[args.target_sha] = check_sha(repo, args.target_sha, args.test_path, db_url, args.source_sha)

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
