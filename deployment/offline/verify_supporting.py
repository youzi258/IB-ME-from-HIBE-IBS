"""Verify extracted supporting files with bounded memory, including large images."""
import hashlib
import json
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "文件清单.json").read_text(encoding="utf-8"))
    failures, seen = [], set()
    for record in manifest["files"]:
        name = record["path"]
        target = (root / name).resolve()
        if name in seen or not target.is_relative_to(root) or target == root:
            raise ValueError("invalid or duplicate manifest path")
        seen.add(name)
        if not target.is_file():
            failures.append({"path": name, "reason": "missing"})
            continue
        with target.open("rb") as stream:
            value = hashlib.file_digest(stream, "sha256").hexdigest()
        if target.stat().st_size != record["bytes"] or value != record["sha256"]:
            failures.append({"path": name, "reason": "changed"})
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    for extra in sorted(actual - seen - {"文件清单.json", "SHA256SUMS.txt"}):
        failures.append({"path": extra, "reason": "unexpected"})
    print(json.dumps({"status": "failed" if failures else "passed", "files": len(seen), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
