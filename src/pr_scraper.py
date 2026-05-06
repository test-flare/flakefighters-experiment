"""
This module uses the  GitHub API to look for actions that were run, failed, rerun, and passed.
Results are saved to JSON in the specified location.
"""

import io
import json
import os
import tomllib
import zipfile
from datetime import datetime
from tempfile import TemporaryDirectory
from tqdm import tqdm

import git
import requests
from dotenv import load_dotenv
from github import Auth, Github, Repository
from numpy import linspace

from reproduce_flakiness import parse_test_failures

load_dotenv()

# --- Configuration ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "home-assistant/core"
BASE = "dev"
WORKFLOW_NAME = "ci.yaml"
MAX_RUNS = 50  # Number of recent successful runs to check
REPO_PATH = "./core"
LOCAL_REPO = git.Repo(REPO_PATH)
# HEAD = "ebd1f1b00f931095039973b40fe60355575cc781"
HEAD = "5d091d25d5e59919533a2abaa754259652ea6872"


def get_failed_tests_from_logs(zip_content: str):
    """
    Take the zip output and parse test failures from the log.
    :param zip_content: The content of the zip file.
    """
    failed_tests = []

    with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
        for filename in z.namelist():
            with z.open(filename) as f:
                content = f.read().decode("utf-8", errors="ignore")
                failed_tests += parse_test_failures(content)
    return failed_tests


def requires_python(sha: str):
    """
    Returns the required python version string (if found) for a given commit sha.
    :param sha: The commit sha.
    """

    with TemporaryDirectory() as worktree_path:
        LOCAL_REPO.git.worktree("add", worktree_path, sha)
        if os.path.exists(f"{worktree_path}/.python_version"):
            with open(f"{worktree_path}/.python_version") as f:
                return "\n".join(f.readlines()).strip()
        if os.path.exists(f"{worktree_path}/pyproject.toml"):
            with open(f"{worktree_path}/pyproject.toml", "rb") as f:
                return tomllib.load(f).get("project", {}).get("requires-python", "")
    return ""


def get_test_metadata(
    test_id: str,
    head_commit: str = "HEAD",
    commit_sample_size: int = 0,
) -> dict:
    """
    Finds the commit that introduced a test return an evenly spaced sample of commits between then and the head commit.

    :param test_id: The full identifier of the test,
                    e.g. "tests/components/bang_olufsen/test_event.py::test_button_event_creation_a5".
    :param head_commit: The commit hash representing the current moment in time. Defaults to HEAD.
    :param commit_sample_size: How many commits to return in the sample.
    """
    # Find the commit that introduced the test function definition
    try:
        file_path, test_name = test_id.split("::")

        log_output = LOCAL_REPO.git.log(f"-L:{test_name}:{file_path}", "--reverse", "--format=%H", "--no-patch")
        introduction_commit_sha = log_output.strip().split("\n")[0]
        introduction_date = LOCAL_REPO.commit(introduction_commit_sha).committed_datetime.isoformat()

        if not commit_sample_size:
            return {
                "introduced_in": introduction_commit_sha,
                "introduction_date": introduction_date,
            }

        commits_since_introduction = list(
            LOCAL_REPO.iter_commits(f"{introduction_commit_sha}..{head_commit}", first_parent=True)
        )
        commits_since_introduction += list(commits_since_introduction[-1].parents)

        commits_since_introduction.reverse()

        assert LOCAL_REPO.commit(head_commit) in commits_since_introduction, f"Head commit {head_commit} not in history"
        assert (
            LOCAL_REPO.commit(introduction_commit_sha) in commits_since_introduction
        ), f"Introduction commit {introduction_commit_sha} not in history"

        commit_sample = [LOCAL_REPO.commit(introduction_commit_sha).parents[0].hexsha] + [  # Commit before introduction
            commits_since_introduction[round(i)].hexsha
            for i in linspace(0, len(commits_since_introduction) - 1, commit_sample_size)
        ]

        return {
            "introduced_in": introduction_commit_sha,
            "introduction_date": introduction_date,
            "commits_since_introduction": len(commits_since_introduction),
            "commit_sample": sorted(
                [
                    {
                        "sha": sha,
                        "committed_datetime": LOCAL_REPO.commit(sha).committed_datetime.isoformat(),
                        "requires_python": requires_python(sha),
                    }
                    for sha in commit_sample
                ],
                key=lambda x: datetime.fromisoformat(x["committed_datetime"]),
            ),
        }
    except git.exc.GitCommandError:
        return None


def get_run_metadata(remote: Repository, run: dict) -> dict:
    """
    Finds the commit hashes associated with the run, and identifies flaky test candidates.

    :param remote: The GitHub Repository.
    :param run: The workflow run.
    """
    log_url = f"https://api.github.com/repos/{REPO_NAME}/actions/runs/{run['id']}/attempts/1/logs"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    response = requests.get(log_url, headers=headers, timeout=30)
    pulls = remote.get_commit(run["head_sha"]).get_pulls()

    if response.status_code == 200 and pulls.totalCount > 0:
        pr = pulls[0]
        failed_tests = []
        for test_id in get_failed_tests_from_logs(response.content):
            test_metadata = get_test_metadata(test_id, head_commit=HEAD)
            if test_metadata:
                failed_tests.append({"test_id": test_id} | test_metadata)

        if failed_tests:
            return {
                "run_id": run["id"],
                "run_attempt": run["run_attempt"],
                "failed_tests": failed_tests,
                "pr_number": pr.number,
                "pr_title": pr.title,
                "pr_created_at": pr.created_at.isoformat(),
                # The Merge Commit created by GitHub for the CI run
                "merge_commit_sha": run["head_sha"],
                # The Source (Feature Branch) commit
                "source_sha": pr.head.sha,
                # The Target (Base Branch, e.g., dev) commit
                "target_sha": pr.base.sha,
            }
    return None


def main():
    """
    Main entrypoint. Scrape the repo and save the result to JSON.
    """
    remote = Github(auth=Auth.Token(GITHUB_TOKEN)).get_repo(REPO_NAME)
    found_count = 0
    data = []

    # url = f"https://api.github.com/repos/{REPO_NAME}/actions/runs"
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_NAME}/runs"
    params = {
        # "state": "closed",
        "status": "completed",
        "base": BASE,
        # "name": WORKFLOW_NAME,
        "sort": "updated",
        "direction": "desc",
        "per_page": 100,
    }
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

    # Pagination loop for PRs (GitHub API returns 100 max per page)
    while url and found_count < MAX_RUNS:
        print(url)
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        runs = response.json()
        if not runs:
            break
        viable_runs = list(
            filter(
                lambda run: run["run_attempt"] > 1 or run["conclusion"] != "success",
                runs["workflow_runs"],
            )
        )
        print(f"  {len(viable_runs)} viable runs")

        for run in tqdm(viable_runs):
            metadata = get_run_metadata(remote, run)
            if metadata is not None:
                data.append(metadata)
                found_count += 1

        # with Pool() as pool:
        #     metadata = list(
        #         filter(
        #             lambda x: x is not None,
        #             pool.starmap(
        #                 get_run_metadata,
        #                 map(lambda run: (remote, run), viable_runs),
        #             ),
        #         )
        #     )
        with open(f"home_assistant_flakes_{BASE}.json", "w") as f:
            json.dump(data, f, indent=2)
        if "next" in response.links and url:
            url = response.links["next"]["url"]
        else:
            break


if __name__ == "__main__":
    main()
