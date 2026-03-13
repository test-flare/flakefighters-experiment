import argparse
import json
import os
import subprocess
import re
import sys
import tomllib

from glob import glob

from git import Repo


# --- Configuration ---
REPO_PATH = "./core"  # Path where the repo will be cloned
REPO_URL = "https://github.com/home-assistant/core.git"
ITERATIONS = 2

replacements = {
    r"mypy\-dev==\d+\.\d+\.\w+": "mypy-dev",
    r"aioasuswrt==1\.5\.1": "aioasuswrt==1.5.2",
}


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
    package_constraints = os.path.join(REPO_PATH, "homeassistant/package_constraints.txt")
    pycares_5 = False
    josepy_2 = False
    for fname in glob(os.path.join(REPO_PATH, "*requirements*.txt"), recursive=True) + [package_constraints]:
        with open(fname) as f:
            packages = f.readlines()
        for old, new in replacements.items():
            packages = [re.sub(old, new, p) for p in packages]
        if any("aiodns==3" in line for line in packages):
            print("PYCARES_5")
            pycares_5 = True
        if any("hass-nabucasa==0.8" in line for line in packages):
            print("josepy_2")
            josepy_2 = True
        with open(fname, "w") as f:
            f.write("\n".join(packages))
        os.makedirs(f"outputs/{os.path.split(fname)[0]}", exist_ok=True)
        with open(f"outputs/{fname}", "w") as f:
            f.write("\n".join(packages))
        with open(package_constraints, "a") as f:
            if pycares_5:
                # aiodns depends on pycares, but is not sufficiently strict on versioning:
                # pycares 5+ is not compatible with python 3.14
                f.write("pycares<5\n")
            if josepy_2:
                f.write("josepy<2\n")  # module 'josepy' has no attribute 'ComparableX509'

    setup_result = subprocess.run(
        "./script/setup",
        check=False,
        shell=True,
        cwd=REPO_PATH,
        capture_output=True,
    )
    extra_requirements_result = subprocess.run(
        "pip install -r requirements_all.txt",
        check=False,
        shell=True,
        cwd=REPO_PATH,
        capture_output=True,
    )

    # TODO: Pip install flakefighters here to get correct versions of pytest and coverage, etc.

    if setup_result.returncode != 0 or extra_requirements_result.returncode != 0:
        return {"successes": None, "failures": None, "confirmed": None, "error": setup_result.stderr.decode("utf-8")}

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

        print(f"pytest {test_to_run} --database-url={db_url} --flakefighters")
        process = subprocess.run(
            f"pytest {test_to_run} --database-url={db_url} --flakefighters",
            shell=True,
            cwd=REPO_PATH,
            capture_output=True,
            check=False,
        )
        failed_tests = parse_test_failures(process.stdout.decode("utf-8"))
        print("FAILED TESTS", failed_tests)
        print(process.stdout.decode("utf8"))
        print()
        print()
        print(process.stderr.decode("utf8"))

        # if process.returncode == 0:
        if test_path not in failed_tests:
            successes += 1
            test_to_run = test_path
        else:
            failures += 1

    assert setup_result or os.path.exists(db_url), f"No database at {db_url}"
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
    print("python reproduce_flakiness.py", " ".join(sys.argv[1:]))
    parser = argparse.ArgumentParser(
        prog="reproduce_flakiness",
        description="Attempts to reproduce flaky behaviour for a given test case of the home-assistant git repo.",
    )
    parser.add_argument("-s", "--source-sha", help="Source commit sha.")
    parser.add_argument("-t", "--target-sha", help="Target commit sha.")
    parser.add_argument("-T", "--test-path", help="Name of the test to run.")
    parser.add_argument("-o", "--output", help="Output file path.")
    args = parser.parse_args()

    os.makedirs(os.path.split(args.output)[0], exist_ok=True)

    db_url = f"sqlite:///{args.output.replace('.json', '.db')}"

    repo = Repo(REPO_PATH)
    repo.git.reset("--hard")
    repo.git.fetch()

    flakiness = check_sha(repo, args.target_sha, args.test_path, db_url, args.source_sha)

    python_version = []
    if os.path.exists(f"{REPO_PATH}/.python_version"):
        with open(f"{REPO_PATH}/.python_version") as f:
            python_version.APPEND(f.readline().strip())
    with open(f"{REPO_PATH}/pyproject.toml", "rb") as f:
        data = tomllib.load(f)
        python_version.append(data.get("project", {}).get("requires-python", ""))
    python_version = ",".join(python_version)

    print("OUTPUT", args.output)
    with open(args.output, "w") as f:
        json.dump(
            {
                "source_sha": args.source_sha,
                "target_sha": args.target_sha,
                "requires_python": python_version,
                "running_python": sys.version,
                "date": repo.commit(args.target_sha).committed_datetime.isoformat(),
                "flaky_test_candidate": args.test_path,
                "flakiness": flakiness,
            },
            f,
            indent=2,
        )


if __name__ == "__main__":
    main()
