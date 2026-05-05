import json
import os
import ast
from git import Repo


def get_source_without_running(file_path, target_name):
    """
    Parses a file and extracts the source of a function or method
    without executing any code.
    """
    with open(file_path, "r") as f:
        node = ast.parse(f.read())

    for item in ast.walk(node):
        # Look for function definitions (FunctionDef)
        # or async function definitions (AsyncFunctionDef)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name == target_name:
                # ast.get_source_segment is available in Python 3.8+
                # It extracts the exact text from the original file
                with open(file_path, "r") as f:
                    full_content = f.read()
                    return ast.get_source_segment(full_content, item)

    return f"Method '{target_name}' not found."


repo = Repo("core")

with open("home_assistant_flakes_dev.json") as f:
    actions = json.load(f)

for action in actions:
    repo.git.fetch("origin", action["target_sha"])
    repo.git.checkout(action["target_sha"])
    for test in action["failed_tests"]:
        print(action["target_sha"])
        file_path, function_name = test["test_id"].split("::")
        _, file_name = os.path.split(file_path)
        with open(os.path.join("core-tests", f"{action['target_sha']}-{file_name}"), "w") as f:
            print("#", os.path.join("core", test["test_id"]), file=f)
            print(get_source_without_running(os.path.join("core", file_path), function_name), file=f)
        # copy(os.path.join("core", file_path), os.path.join("core-tests", f"{action["target_sha"]}-{file_name}"))
