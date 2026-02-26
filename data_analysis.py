import pandas as pd
import json
from glob import glob
from packaging.specifiers import SpecifierSet
from packaging.version import Version


def satisfies_python_requirement(version_str, requirement_str):
    # Parse the version (e.g., "3.13.12")
    version = Version(version_str)

    # Parse the requirement (e.g., ">=3.13.2")
    specifier = SpecifierSet(requirement_str)

    # Check for compatibility
    return version in specifier


data = []
for fname in glob("outputs/**/*.json", recursive=True):
    with open(fname) as f:
        data.append(json.load(f))
data = pd.DataFrame(data)
data["running_python"] = [p.split(" ")[0] for p in data["running_python"]]
data["requires_python"] = [p.split("||")[1] for p in data["requires_python"]]
data["ok"] = [satisfies_python_requirement(v, c) for v, c in zip(data["running_python"], data["requires_python"])]
data.to_csv("results.csv")


print(data[["running_python", "requires_python", "ok", "date"]])
