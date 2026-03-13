import json
import os
import subprocess
from multiprocessing import Pool
import sys
import re

from git import Repo
from reproduce_flakiness import REPO_PATH

JSON_FILE = "home_assistant_flakes_dev.json"


def requires_python(constraint):
    match = re.search(r">=(3\.\d+)", constraint)
    if match:
        return match.group(1)
    return "3.9"


def reproduce_flakiness(args):
    command = (
        f'docker run --rm -v {os.path.join(os.getcwd(), "outputs")}:/outputs flakehunter:{args["python_version"]} '
        # f'docker run --rm -v {os.path.join(os.getcwd(), "outputs")}:/outputs flakehunter '
        f'-t {args["target_sha"]} -T {args["test_id"]} -o /outputs/{args["test_id"]}/{args["target_sha"]}.json'
    )
    if "source_sha" in args:
        command += f" -s {args['source_sha']}"
    subprocess.run(
        command,
        check=False,
        shell=True,
    )


def main():
    if not os.path.exists("outputs"):
        os.mkdir("outputs")

    with open("outputs/.gitignore", "w") as f:
        f.write(".\n*\n")

    with open(JSON_FILE, "r") as f:
        data = json.load(f)

    repo = Repo(REPO_PATH)
    repo.git.reset("--hard")
    repo.git.fetch()

    args = []
    for run in data:
        for test in run["failed_tests"]:
            for commit in test["commit_sample"]:
                python_version = requires_python(commit["requires_python"])
                args.append({"target_sha": commit["sha"], "test_id": test["test_id"], "python_version": python_version})

    hashes = None
    if len(sys.argv) > 1:
        hashes = sys.argv[1:]
    if hashes is not None:
        args = [a for a in args if a["target_sha"] in hashes]

    print("ARGS", args)
    with Pool(8) as pool:
        pool.map(reproduce_flakiness, args)


if __name__ == "__main__":
    main()
