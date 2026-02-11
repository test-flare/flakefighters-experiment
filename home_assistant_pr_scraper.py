import io
import json
import os
import re
import zipfile

import git
import requests
from dotenv import load_dotenv
from github import Auth, Github, Repository
from numpy import linspace

load_dotenv()

# --- Configuration ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "home-assistant/core"
MAX_RUNS = 20  # Number of recent successful runs to check
LOCAL_REPO = git.Repo("../core")


def get_failed_tests_from_logs(zip_content):
    failed_tests = []
    # Pytest failure pattern in logs: FAILED path/to/test.py::test_name
    pytest_fail_regex = re.compile(r"FAILED\s+([\w\/\.\d_]+::[\w\d_]+)")

    with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
        for filename in z.namelist():
            with z.open(filename) as f:
                content = f.read().decode("utf-8", errors="ignore")
                matches = pytest_fail_regex.findall(content)
                for m in matches:
                    if m not in failed_tests:
                        failed_tests.append(m)
    return failed_tests


def get_test_metadata(
    test_id: str,
    head_commit: str = "HEAD",
    commit_sample_size: int = 10,
) -> dict:
    """
    Finds the commit that introduced a test return an evenly spaced sample of commits between then and the head commit.

    :param test_id: The full identifier of the test,
                    e.g. "tests/components/bang_olufsen/test_event.py::test_button_event_creation_a5".
    :param head_commit: The commit hash representing the current moment in time. Defaults to HEAD.
    :param commit_sample_size: How many commits to return in the sample.
    """
    try:
        # Find the commit that introduced the test function definition
        file_path, test_name = test_id.split("::")
        log_output = LOCAL_REPO.git.log(
            f"-L:{test_name}:{file_path}", "--reverse", "--format=%H", "--no-patch"
        )
        introduction_commit_sha = log_output.strip().split("\n")[0]
        commits_since_introduction = list(
            LOCAL_REPO.iter_commits(f"{introduction_commit_sha}..{head_commit}")
        )
        introduction_date = LOCAL_REPO.commit(
            introduction_commit_sha
        ).committed_datetime.isoformat()

        return {
            "introduced_in": introduction_commit_sha,
            "introduction_date": introduction_date,
            "commits_since_introduction": len(commits_since_introduction),
            "commit_sample": [
                commits_since_introduction[round(i)].hexsha
                for i in linspace(
                    0, len(commits_since_introduction) - 1, commit_sample_size
                )
            ],
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
        flaky_test_candidates = []
        for test_id in get_failed_tests_from_logs(response.content):
            test_metadata = get_test_metadata(test_id)
            if test_metadata:
                flaky_test_candidates.append({"test_id": test_id} | test_metadata)

        if flaky_test_candidates:
            return {
                "run_id": run["id"],
                "run_attempt": run["run_attempt"],
                "flaky_test_candidates": flaky_test_candidates,
                "pr_number": pr.number,
                "pr_title": pr.title,
                # The Merge Commit created by GitHub for the CI run
                "merge_commit_sha": run["head_sha"],
                # The Source (Feature Branch) commit
                "source_sha": pr.head.sha,
                # The Target (Base Branch, e.g., dev) commit
                "target_sha": pr.base.sha,
            }
    return None


def main():
    remote = Github(auth=Auth.Token(GITHUB_TOKEN)).get_repo(REPO_NAME)
    found_count = 0
    data = []

    url = f"https://api.github.com/repos/{REPO_NAME}/actions/runs"
    params = {
        "state": "closed",
        "base": "master",  # or 'main' depending on the branch
        "sort": "updated",
        "direction": "desc",
        "per_page": 100,
    }
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

    # Pagination loop for PRs (GitHub API returns 100 max per page)
    while url:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        runs = response.json()
        if not runs:
            break
        runs = runs["workflow_runs"]
        for run in runs:
            if found_count >= MAX_RUNS:
                break
            if run["run_attempt"] > 1:
                datum = get_run_metadata(remote, run)
                if datum is not None:
                    data.append(datum)
                    found_count += 1
        with open("home_assistant_flakes2.json", "w") as f:
            json.dump(data, f, indent=2)
        if "next" in response.links and url:
            url = response.links["next"]["url"]
        else:
            break


if __name__ == "__main__":
    main()
