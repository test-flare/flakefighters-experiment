import json
import os
import subprocess
from multiprocessing import Pool

JSON_FILE = "home_assistant_flakes.json"


def reproduce_flakiness(source_sha, target_sha, test_path):
    subprocess.run(
        f'docker run --rm -v {os.path.join(os.getcwd(), "outputs")}:/outputs flakehunter {source_sha} {target_sha} "{test_path}"     /outputs/{test_path.replace("/", "-")}.json',
        check=False,
        shell=True,
    )


def main():
    with open(JSON_FILE, "r") as f:
        data = json.load(f)

    args = [
        (test["source_sha"], test["target_sha"], test_path)
        for test in data[:6]
        for test_path in test["flaky_test_candidates"]
    ]
    print("ARGS", args)
    with Pool(6) as pool:
        pool.starmap(reproduce_flakiness, args)


if __name__ == "__main__":
    main()
