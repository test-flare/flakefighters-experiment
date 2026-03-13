import json
import tomllib
import os
from git import Repo
from tqdm import tqdm
import datetime


JSON_FILE = "home_assistant_flakes_dev_old.json"
REPO_PATH = "./core"  # Path where the repo will be cloned
repo = Repo(REPO_PATH)


def requires_python(sha):
    repo.git.checkout("-f", sha)
    if os.path.exists(f"{REPO_PATH}/.python_version"):
        with open(f"{REPO_PATH}/.python_version") as f:
            return "\n".join(f.readlines()).strip()
    if os.path.exists(f"{REPO_PATH}/pyproject.toml"):
        with open(f"{REPO_PATH}/pyproject.toml", "rb") as f:
            return tomllib.load(f).get("project", {}).get("requires-python", "")
    return ""


with open(JSON_FILE, "r") as f:
    data = json.load(f)

for run in data:
    for test in run["failed_tests"]:
        test["commit_sample"] = sorted(
            [
                {
                    "sha": sha,
                    "committed_datetime": repo.commit(sha).committed_datetime.isoformat(),
                    "requires_python": requires_python(sha),
                }
                for sha in test["commit_sample"]
            ],
            key=lambda x: datetime.datetime.fromisoformat(x["committed_datetime"]),
        )

with open(JSON_FILE.replace("_old.json", ".json"), "w") as f:
    json.dump(data, f, indent=2)
