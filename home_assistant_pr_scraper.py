import io
import json
import os
import re
import zipfile

import requests
from dotenv import load_dotenv
from git import Repo
from github import Auth, Github
from numpy import linspace

load_dotenv()

# --- Configuration ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "home-assistant/core"
MAX_RUNS = 50  # Number of recent successful runs to check
LOCAL_REPO = Repo("./core")


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


def run_datum(remote, run):
    log_url = f"https://api.github.com/repos/{REPO_NAME}/actions/runs/{run.id}/attempts/1/logs"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(log_url, headers=headers, timeout=30)
    pulls = remote.get_commit(run.head_sha).get_pulls()

    if response.status_code == 200 and pulls.totalCount > 0:
        pr = pulls[0]
        flaky_tests = get_failed_tests_from_logs(response.content)
        if flaky_tests:
            return {
                "run_id": run.id,
                "run_attempt": run.run_attempt,
                "flaky_test_candidates": [
                    {"test_id": test_id} | get_test_metadata(test_id)
                    for test_id in flaky_tests
                ],
                "pr_number": pr.number,
                "pr_title": pr.title,
                # The Merge Commit created by GitHub for the CI run
                "merge_commit_sha": run.head_sha,
                # The Source (Feature Branch) commit
                "source_sha": pr.head.sha,
                # The Target (Base Branch, e.g., dev) commit
                "target_sha": pr.base.sha,
            }
    return None


def main():
    run_ids = [
        # 21449219805,
        # 21446895624,
        # 21431943649,
        # 21431522901,
        # 21431137197,
        # 21431095563,
        # 21430678742,
        # 21430633954,
        # 21429397552,
        # 21420612878,
        # 21417739495,
        # 21388188984,
        # 21384161812,
        # 21343142119,
        # 21338669930,
        # 21325525765,
        # 21312963300,
    ]
    g = Github(auth=Auth.Token(GITHUB_TOKEN))
    remote = g.get_repo(REPO_NAME)

    # We filter by 'pull_request' event specifically now
    def runs():
        for run in map(remote.get_workflow_run, run_ids):
            yield run
        for run in remote.get_workflow_runs(event="pull_request", status="success"):
            yield run

    found_count = 0
    data = []
    for run in runs():
        if found_count >= MAX_RUNS:
            break
        if run.run_attempt > 1:
            found_count += 1
            datum = run_datum(remote, run)
            if datum is not None:
                data.append(datum)

    with open("home_assistant_flakes2.json", "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
