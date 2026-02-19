import json
import os
import subprocess
from multiprocessing import Pool

JSON_FILE = "home_assistant_flakes3.json"


def reproduce_flakiness(source_sha, target_sha, test_path, sample_shas):
    subprocess.run(
        f'docker run --rm -v {os.path.join(os.getcwd(), "outputs")}:/outputs flakehunter {source_sha} {target_sha} "{test_path}"     /outputs/{test_path.replace("/", "-")}.json "{" ".join(sample_shas)}"',
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

    args = [
        (run["source_sha"], run["target_sha"], test["test_id"], test["commit_sample"])
        for run in data
        for test in run["failed_tests"]
    ]
    print("ARGS", args)
    with Pool(6) as pool:
        pool.starmap(reproduce_flakiness, args)


if __name__ == "__main__":
    main()
