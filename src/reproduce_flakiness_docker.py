"""
This module implements the main entrypoint for the experiments.
It takes in a JSON file representing the failed runs and attempts to reproduce the flakiness.
"""

import json
import os
import sys
from multiprocessing import Pool
import docker

JSON_FILE = "home_assistant_flakes_dev.json"
REPO_PATH = "./core"
client = docker.from_env()


def reproduce_flakiness(test: dict):
    """
    Given a failing test, try to reproduce the flaky behaviour and identify it with flakefighters.
    :param test: Dictionary representing the test to reproduce.
    """

    command = (
        f"-t {test['target_sha']} "
        f"-T {test['test_id']} "
        f"-o /home/flakehunter/outputs/{test['test_id']}/{test['target_sha']}.json "
        f"-r 1000 "
        f"-R {REPO_PATH}"
    )
    if "source_sha" in test:
        command += f" -s {test['source_sha']}"

    container = client.containers.create(
        f"flakehunter:{test['python_version']}",
        command,
        volumes={os.path.join(os.getcwd(), "outputs"): {"bind": "/home/flakehunter/outputs", "mode": "rw"}},
    )
    container.start()
    result = container.wait()
    exit_code = result.get("StatusCode")
    logs = container.logs().decode("utf-8")

    if exit_code != 0:
        print(f"Container failed with exit code {exit_code}")
        print("--- Captured Logs ---")
        print(logs if logs else "No logs captured.")

    container.remove()


def main():
    """
    Main entrypoint for the experiments.
    """
    if not os.path.exists("outputs"):
        os.mkdir("outputs")

    with open("outputs/.gitignore", "w") as f:
        f.write(".\n*\n")

    with open(JSON_FILE, "r") as f:
        data = json.load(f)

    args = []
    for run in data:
        for test in run["failed_tests"]:
            args.extend(
                [
                    {
                        "target_sha": run["source_sha"],
                        "test_id": test["test_id"],
                        "python_version": "3.14",
                    },
                    {
                        "target_sha": run["target_sha"],
                        "source_sha": run["source_sha"],
                        "test_id": test["test_id"],
                        "python_version": "3.14",
                    },
                ]
            )

    hashes = None
    if len(sys.argv) > 1:
        hashes = sys.argv[1:]
    if hashes is not None:
        args = [a for a in args if a["target_sha"] in hashes]

    args = list(
        filter(
            lambda arg: not os.path.exists(f"/home/flakehunter/outputs/{arg['test_id']}/{arg['target_sha']}.json"), args
        )
    )

    print("ARGS", args)
    with Pool() as pool:
        try:
            pool.map(reproduce_flakiness, args)
        except KeyboardInterrupt:
            pool.terminate()
            for container in client.containers.list():
                print(f"Killing {container}")
                container.kill()


if __name__ == "__main__":
    main()
