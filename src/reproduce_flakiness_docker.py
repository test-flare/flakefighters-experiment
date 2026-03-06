import json
import os
import subprocess
from multiprocessing import Pool
from datetime import datetime
import sys

from git import Repo
from reproduce_flakiness import REPO_PATH

JSON_FILE = "home_assistant_flakes_dev.json"


def get_python_requirement(repo, sha):
    if repo.commit(sha).committed_datetime.timestamp() < datetime(2023, 8, 1).timestamp():  # date 3.12 came out
        return "3.11"
    if repo.commit(sha).committed_datetime.timestamp() < datetime(2024, 10, 1).timestamp():  # date 3.13 came out
        return "3.12"
    if repo.commit(sha).committed_datetime.timestamp() < datetime(2026, 2, 2).timestamp():  # Date switching to 3.14
        return "3.13"
    return "3.14"
    # repo.git.checkout("--force", sha)
    #
    # with open("pyproject.toml", "rb") as f:
    #     data = tomllib.load(f)
    # if "3.13" in data.get("project", {}).get("requires-python"):
    #     return "13"
    # return "14"


def reproduce_flakiness(args):
    command = (
        f'docker run --rm -v {os.path.join(os.getcwd(), "outputs")}:/outputs flakehunter:{args["python_version"]} '
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
            python_version = get_python_requirement(repo, run["target_sha"])
            args.append(
                {
                    "source_sha": run["source_sha"],
                    "target_sha": run["target_sha"],
                    "test_id": test["test_id"],
                    "python_version": python_version,
                }
            )
            for commit_sha in test["commit_sample"]:
                python_version = get_python_requirement(repo, commit_sha)
                args.append({"target_sha": commit_sha, "test_id": test["test_id"], "python_version": python_version})

    # args = [
    #     (run["source_sha"], run["target_sha"], test["test_id"], test["commit_sample"])
    #     for run in data
    #     for test in run["failed_tests"]
    # ]
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
