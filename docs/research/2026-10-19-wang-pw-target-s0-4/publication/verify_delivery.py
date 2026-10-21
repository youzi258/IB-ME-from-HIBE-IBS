"""Verify the published Git blobs and archived public receipts, not security."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def require(condition, message):
    if not condition:
        raise ValueError(message)


def observations(value):
    if isinstance(value, dict):
        return sum(observations(child) for child in value.values())
    require(value is True, "a recorded observation is not true")
    return 1


def verify_receipt(receipt):
    require(receipt.get("status") == "passed", "receipt status is not passed")
    count = observations(receipt.get("observations", {}))
    for child in receipt.get("child_receipts", []):
        count += verify_receipt(child)
    return count


def junit(data):
    tree = ET.fromstring(data)
    suites = [tree] if tree.tag == "testsuite" else list(tree.findall("testsuite"))
    totals = {name: sum(int(s.get(name, "0")) for s in suites) for name in ("tests", "errors", "failures", "skipped")}
    passed, failed = set(), set()
    for case in tree.iter("testcase"):
        key = (case.get("classname"), case.get("name"))
        if case.find("failure") is not None or case.find("error") is not None:
            failed.add(key)
        elif case.find("skipped") is None:
            passed.add(key)
    return totals, passed, failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="store_true", help="verify the staged merge before its commit")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    root = directory.parents[3]

    def read_blob(path):
        target = ":" + path if args.index else "HEAD:" + path
        return subprocess.check_output(["git", "cat-file", "blob", target], cwd=root)

    relative = directory.relative_to(root).as_posix()
    manifest = json.loads(read_blob(relative + "/manifest.json"))
    entries = manifest["files"]
    require(len({entry["path"] for entry in entries}) == len(entries), "duplicate manifest paths")
    for entry in entries:
        path = Path(entry["path"])
        require(not path.is_absolute() and ".." not in path.parts, "invalid manifest path")
        data = read_blob(path.as_posix())
        require(len(data) == entry["bytes"], "byte count mismatch: " + path.as_posix())
        require(hashlib.sha256(data).hexdigest() == entry["sha256"], "hash mismatch: " + path.as_posix())

    review = json.loads(read_blob(relative + "/review.json"))
    count = 0
    for path in review["target_public_receipts"]:
        count += verify_receipt(json.loads(read_blob(path)))
    totals, passed, failed = junit(read_blob(relative + "/regression.xml"))
    initial, initial_passed, initial_failed = junit(read_blob(relative + "/initial-regression.xml"))
    require(totals == review["regression"]["junit_totals"], "regression totals differ")
    require(totals["errors"] == totals["failures"] == 0, "regression failed")
    require(initial == review["initial_regression"]["junit_totals"], "initial totals differ")
    require(initial_failed <= passed, "the initial failures lack a passing follow-up")
    require(len(initial_passed | passed) == review["regression"]["unique_passed_across_both_runs"], "unique coverage differs")
    require(review["security"]["quantum_bits_status"] == "project-working-assumption-only", "claim scope differs")
    require(review["target_receipts_bind_current_source_snapshot"] is False, "historical source binding was upgraded")
    print(json.dumps({"status": "passed", "git_files": len(entries), "public_receipts": len(review["target_public_receipts"]),
                      "true_observations_including_children": count, "regression": totals,
                      "unique_passing_cases": len(initial_passed | passed),
                      "scope": "Git archive integrity and recorded observations only; no security proof or new target run"}))


if __name__ == "__main__":
    main()
