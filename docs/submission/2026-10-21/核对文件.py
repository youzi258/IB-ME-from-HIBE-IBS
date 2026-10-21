"""Verify extracted supporting files without importing project or crypto code."""
import hashlib
import json
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "文件清单.json").read_text(encoding="utf-8"))
    failures = []
    seen = set()
    for record in manifest["files"]:
        name = record["path"]
        target = (root / name).resolve()
        if name in seen or not target.is_relative_to(root) or target == root:
            raise ValueError("invalid or duplicate manifest path")
        seen.add(name)
        if not target.is_file():
            failures.append({"path": name, "reason": "missing"})
        else:
            raw = target.read_bytes()
            if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
                failures.append({"path": name, "reason": "changed"})
    print(json.dumps({"status": "failed" if failures else "passed", "files": len(seen), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
