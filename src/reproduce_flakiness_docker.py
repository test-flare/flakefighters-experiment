import json
import os
import re
import sys
from multiprocessing import Pool
import docker

JSON_FILE = "home_assistant_flakes_dev.json"
REPO_PATH = "./core"
client = docker.from_env()


def requires_python(constraint):
    match = re.search(r">=(3\.\d+)", constraint)
    if match:
        return match.group(1)
    return "3.10"


def reproduce_flakiness(args):

    command = (
        f"-t {args['target_sha']} "
        f"-T {args['test_id']} "
        f"-o /home/flakehunter/outputs/{args['test_id']}/{args['target_sha']}.json "
        f"-r 2 "
        f"-R {REPO_PATH}"
    )
    if "source_sha" in args:
        command += f" -s {args['source_sha']}"

    # logs = client.containers.run(
    #     image=f"flakehunter:{args['python_version']}",
    #     command=command,
    #     volumes={os.path.join(os.getcwd(), "outputs"): {"bind": "/home/flakehunter/outputs", "mode": "rw"}},
    #     auto_remove=True,  # Critical for cleanup
    #     detach=False,  # Keep it in the foreground so we can catch signals
    # )

    container = client.containers.create(
        f"flakehunter:{args['python_version']}",
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
            # for commit in test["commit_sample"]:
            #     python_version = requires_python(commit["requires_python"])
            #     args.append(
            #         {
            #             "target_sha": commit["sha"],
            #             "test_id": test["test_id"],
            #             "python_version": python_version,
            #         }
            #     )

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
    for arg in args:
        reproduce_flakiness(arg)
        print("DONE 1")
    # with Pool() as pool:
    #     try:
    #         pool.map(reproduce_flakiness, args)
    #     except KeyboardInterrupt:
    #         pool.terminate()
    #         # Use the SDK to find and kill all containers with your session label
    #         for container in client.containers.list():
    #             print(f"Killing {container}")
    #             container.kill()


if __name__ == "__main__":
    main()
