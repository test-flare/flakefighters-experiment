"""
This module attempts to reproduce a flaky test to get it to both pass and fail.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from glob import glob
import time

from git import Repo


def parse_test_failures(log: str) -> list[str]:
    """
    Parse the names of failed tests from the pytest log.
    :param log: The pytest log content.
    :returns: A list of the identifiers of the failed tests.
    """
    failed_tests = []
    # Pytest failure pattern in logs: FAILED path/to/test.py::test_name
    pytest_fail_regex = re.compile(r"(FAILED|ERROR|FLAKY)\s+([\w\/\.\d_]+::[\w\d_]+)")
    matches = pytest_fail_regex.findall(log)
    for m in matches:
        if m not in failed_tests:
            failed_tests.append(m[-1])
    return failed_tests


class FlakinessReproducer:
    """
        Class to reproduce the flakiness of a given test.
    :ivar repo: The Repositry object.
    :ivar test_path: The test identifier (a directory, file, or ::test_id)
    :ivar db_url: The URL where flakefighters should save the run results.
    :ivar repeats: The number of times to run each test.
    """

    def __init__(self, repo_path: str, test_path: str, db_url: str, repeats: int):
        self.repo_path = repo_path
        self.test_path = test_path
        self.db_url = db_url
        self.repeats = repeats

    def fix_dependencies(self):
        """
        Apply workarounds for missing dependencies.
        """
        replacements = {
            r"mypy\-dev==\d+\.\d+\.\w+": "mypy-dev",
            r"aioasuswrt==1\.5\.1": "aioasuswrt==1.5.2",
            # No longer availble in any form, but not necessary for the tests we need to run so we comment it out
            "pyunifiprotect": "#pyunifiprotect",
            "pymazda": "#pymazda",
            "urllib3>=1.26.5": "urllib3<1.27,>=1.21.1",
            # Conflicting sub-dependencies (not required for testing)
            "ibm-watson": "#ibm-watson",
            "mycroftapi": "#mycroftapi",
            "pysmarty": "#pysmarty",
            "pytradfri": "#pytradfri",
            "pycocotools": "#pycocotools",
        }
        package_constraints = os.path.join(self.repo_path, "homeassistant/package_constraints.txt")
        constraints = set()
        for fname in glob(os.path.join(self.repo_path, "*requirements*.txt"), recursive=True) + [package_constraints]:
            with open(fname) as f:
                packages = f.readlines()
            for old, new in replacements.items():
                packages = [re.sub(old, new, p) for p in packages]
            if any("aiodns==3" in line for line in packages):
                # aiodns depends on pycares, but is not sufficiently strict on versioning:
                # pycares 5+ is not compatible with python 3.14
                constraints.add("pycares<5")
            if any("hass-nabucasa==0.8" in line for line in packages):
                # module 'josepy' has no attribute 'ComparableX509'
                constraints.add("josepy<2")
            if any("requests==2.28.1" in line for line in packages):
                # requests 2.28.1 requires urllib3<1.27,>=1.21.1
                constraints.add("urllib3<1.27,>=1.21.1")
            with open(fname, "w") as f:
                f.write("\n".join(packages))
            with open(package_constraints, "a") as f:
                for constraint in constraints:
                    f.write(constraint + "\n")

    def configure_pyproject(self):
        """
        Add the flakefighters config to the pyproject.toml file
        """
        with open(os.path.join(self.repo_path, "pyproject.toml"), "a") as f:
            f.write(
                """
            [tool.pytest.ini_options.pytest_flakefighters.flakefighters.diffcov.DiffCov]
            run_live=false

            [tool.pytest.ini_options.pytest_flakefighters.flakefighters.traceback_matching.TracebackMatching]
            run_live=false

            [tool.pytest.ini_options.pytest_flakefighters.flakefighters.traceback_matching.CosineSimilarity]
            run_live=false

            [tool.pytest.ini_options.pytest_flakefighters.flakefighters.coverage_independence.CoverageIndependence]
            run_live=false
            """
            )

    def search_for_flakiness(self) -> dict[str, int]:
        """
        Try to reporoduce the flakiness for a given test in the given repo.
        :returns: Dictionary of the number of passes and failures for the given test.
        """
        self.fix_dependencies()
        self.configure_pyproject()

        command = "pip install -r requirements_all.txt --constraint homeassistant/package_constraints.txt; pip install -r requirements_test.txt --constraint homeassistant/package_constraints.txt"

        if "3.9" in sys.version:
            command = "pip install setuptools==68; " + command

        setup_result = subprocess.run(
            command,
            check=False,
            shell=True,
            cwd=self.repo_path,
            capture_output=True,
        )

        if setup_result.returncode != 0:
            print(setup_result.stdout.decode("utf-8"))
            print(setup_result.stderr.decode("utf-8"))
            return {
                "successes": None,
                "failures": None,
                "confirmed": None,
                "stdout": setup_result.stdout.decode("utf-8"),
                "stderr": setup_result.stderr.decode("utf-8"),
            }

        successes = 0
        failures = 0
        confirmed = False

        test_to_run = self.test_path.split("::")[0]
        flakefighters_runtime = None
        no_flakefighters_runtime = None

        for i in range(self.repeats):

            flakefighters_start = time.time()
            process = subprocess.run(
                f"pytest {test_to_run} --database-url={self.db_url} --flakefighters",
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                check=False,
            )
            flakefighters_end = time.time()
            if not i:
                flakefighters_runtime = flakefighters_end - flakefighters_start
                no_flakefighters_start = time.time()
                process = subprocess.run(
                    f"pytest {test_to_run}",
                    shell=True,
                    cwd=self.repo_path,
                    capture_output=True,
                    check=False,
                )
                no_flakefighters_end = time.time()
                no_flakefighters_runtime = no_flakefighters_end - no_flakefighters_start

            if self.test_path not in parse_test_failures(process.stdout.decode("utf-8")):
                successes += 1
                # We want to run the whole test suite once and then just the flaky test candidate
                test_to_run = self.test_path
            else:
                failures += 1
            if successes and failures:
                confirmed = True
                break

        print("CONFIRMED", confirmed)
        return {
            "successes": successes,
            "failures": failures,
            "confirmed": confirmed,
            "flakefighters_runtime": flakefighters_runtime,
            "no_flakefighters_runtime": no_flakefighters_runtime,
            "stdout": process.stdout.decode("utf-8"),
            "stderr": process.stderr.decode("utf-8"),
        }

    def check_sha(self, target_sha: str, source_sha: str = None) -> dict[str, int]:
        """
        Checkout the target SHA, search for flakiness, and clean up when done.
        :ivar target_sha: The target SHA.
        :ivar source_sha: The source SHA (if the target_sha represents a pull request).
        :returns: Dictionary of the number of passes and failures for the given test.
        """
        repo = Repo(self.repo_path)
        repo.git.reset("--hard")
        repo.git.fetch("origin", target_sha)
        repo.git.checkout(target_sha)
        if source_sha is not None:
            repo.remotes.origin.fetch(source_sha)
            repo.git.merge("FETCH_HEAD")

        flakiness = self.search_for_flakiness()
        repo.git.reset("--hard")
        return flakiness


def main():
    """
    Main method. Search for flakiness for a given SHA and save the results to JSON.
    """
    print("python reproduce_flakiness.py", " ".join(sys.argv[1:]))
    parser = argparse.ArgumentParser(
        prog="reproduce_flakiness",
        description="Attempts to reproduce flaky behaviour for a given test case of the home-assistant git repo.",
    )
    parser.add_argument("-s", "--source-sha", help="Source commit sha.")
    parser.add_argument("-t", "--target-sha", help="Target commit sha.")
    parser.add_argument("-T", "--test-path", help="Name of the test to run.")
    parser.add_argument("-o", "--output", help="Output file path.")
    parser.add_argument("-r", "--repeats", type=int, help="The number of times to run each test.")
    parser.add_argument("-R", "--repo_path", help="The root directory of the repo.")
    args = parser.parse_args()

    os.makedirs(os.path.split(args.output)[0], exist_ok=True)

    db_url = f"sqlite:///{args.output.replace('.json', '.db')}"

    flakiness_reproducer = FlakinessReproducer(args.repo_path, args.test_path, db_url, args.repeats)
    flakiness = flakiness_reproducer.check_sha(args.target_sha, args.source_sha)

    with open(args.output, "w") as f:
        json.dump(
            {
                "source_sha": args.source_sha,
                "target_sha": args.target_sha,
                "running_python": sys.version,
                "test_id": args.test_path,
                "flakiness": flakiness,
            },
            f,
            indent=2,
        )


if __name__ == "__main__":
    main()
