"""Recompute anonymous PR90 evidence; never call cryptographic measurements."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sys
import tempfile
import zipfile


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_wheel_members(names):
    seen = set()
    for name in names:
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                or name.casefold() in seen):
            raise ValueError("invalid wheel member")
        seen.add(name.casefold())


def replace_execution(value, old, new):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "execution_digest":
                if item != old:
                    raise ValueError("mixed original execution fingerprint")
                value[key] = new
            else:
                replace_execution(item, old, new)
    elif isinstance(value, list):
        for item in value:
            replace_execution(item, old, new)


def write_json(path, data):
    path.write_bytes((json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())


def audit_copy(source, target, original_digest, anonymous_digest):
    """Rebind only temporary audit identities and their checkpoint hashes."""
    source, target = Path(source), Path(target)
    target.mkdir(parents=True, exist_ok=False)
    paths = [source / "batch-manifest.json", source / "environment.json"]
    paths.extend(sorted((source / "jobs").glob("*.json")))
    for path in paths:
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        value = json.loads(path.read_bytes())
        replace_execution(value, original_digest, anonymous_digest)
        write_json(destination, value)
    for state_path in (target / "jobs").glob("*-state.json"):
        value = json.loads(state_path.read_bytes())
        stem = state_path.name.removesuffix("-state.json")
        for mode in ("generation", "restore"):
            if "sha256" in value.get(mode, {}):
                value[mode]["sha256"] = file_digest(state_path.parent / (stem + "-" + mode + ".json"))
        write_json(state_path, value)


def assert_same_statistics(expected, actual):
    """Only anonymous execution/source identity bookkeeping may differ."""
    left, right = copy.deepcopy(expected), copy.deepcopy(actual)
    for value in (left, right):
        value.pop("execution_digest")
        value["design"].pop("execution_digest")
        for provenance in value["sources"].values():
            provenance.pop("source_files")
    if left != right:
        raise ValueError("recomputed statistics differ from the archived result")


def verify_files(root, records):
    for name, record in records.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or path.is_symlink():
            raise ValueError("missing or invalid evidence path: " + name)
        if file_digest(path) != record["sha256"]:
            raise ValueError("evidence checksum mismatch: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materials", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = args.materials.resolve()
    section = root / "07_十组合性能实验"
    info = json.loads((section / "source-records.json").read_bytes())
    verify_files(root, info["files"])
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise ValueError("output must be outside the submitted materials")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output directory must be empty")
    if sys.version_info[:2] != (3, 12) or sys.platform != "linux" or platform.machine() != "x86_64":
        raise RuntimeError("use the provided Linux amd64 Python 3.12 Docker image")
    with tempfile.TemporaryDirectory(prefix="pr90-recompute-") as temp:
        temporary = Path(temp)
        dependencies = temporary / "dependencies"
        dependencies.mkdir()
        lock = json.loads((section / "wheel-lock.json").read_bytes())
        for item in lock["wheels"]:
            path = section / "wheels" / item["filename"]
            if file_digest(path) != item["sha256"]:
                raise ValueError("offline dependency checksum mismatch")
            with zipfile.ZipFile(path) as archive:
                safe_wheel_members(archive.namelist())
                archive.extractall(dependencies)
        sys.path.insert(0, str(dependencies))
        sys.path.insert(0, str(root / "01_程序源码"))
        os.environ["MPLCONFIGDIR"] = str(temporary / "matplotlib-cache")
        (temporary / "cache").mkdir()
        os.environ["XDG_CACHE_HOME"] = str(temporary / "cache")
        import numpy
        if numpy.__version__ != lock["provided_by_base_image"]["numpy"]:
            raise RuntimeError("NumPy differs from the fixed base image")
        from experiments.research.ten_combination_benchmark import digest, stable_identity
        from experiments.research.ten_combination_basic_comparison import read_verified, combine, write_comparison
        from experiments.research.ten_combination_summary import plots
        design = json.loads((section / "数据/basic-design.json").read_bytes())
        expected = json.loads((section / "结果/basic-summary.json").read_bytes())
        original = design["execution_digest"]
        sources, identity = {}, None
        for batch in (design["reused_batch"], design["supplemental_batch"]):
            source = section / "数据" / batch
            environment = json.loads((source / "environment.json").read_bytes())
            current = digest(stable_identity(environment))
            if identity is not None and current != identity:
                raise ValueError("anonymous source environments differ")
            identity = current
            # Preserve original provenance checks against the archived summary.
            for relative, source_sha in expected["sources"][batch]["source_files"].items():
                name = (source / relative).relative_to(root).as_posix()
                if info["files"][name]["source_sha256"] != source_sha:
                    raise ValueError("original public receipt provenance differs")
            audit = temporary / batch
            audit_copy(source, audit, original, identity)
            sources[batch] = read_verified(audit)
        replace_execution(design, original, identity)
        result = combine(design, sources)
        assert_same_statistics(expected, result)
        if result["status"] != "passed" or result["completed_cases"] != 10:
            raise ValueError("ten complete cases required")
        write_comparison(output, result)
        for name in ("basic-comparison.csv", "basic-comparison.md"):
            if (output / name).read_bytes() != (section / "结果" / name).read_bytes():
                raise ValueError("derived table differs: " + name)
        plots(output, result)
        from PIL import Image
        sizes = {}
        for name in ("operation-times.png", "object-sizes.png"):
            with Image.open(output / name) as image:
                sizes[name] = list(image.size)
                image.verify()
            with Image.open(section / "结果" / name) as original_image:
                if sizes[name] != list(original_image.size):
                    raise ValueError("derived plot dimensions differ")
        tests = None
        if args.self_test:
            import pytest
            tests = pytest.main(["-q", "-p", "no:cacheprovider", "--basetemp", str(temporary / "pytest"),
                                 str(root / "01_程序源码/tests/test_ten_combination_basic_comparison.py"),
                                 str(root / "01_程序源码/tests/test_ten_combination_benchmark.py")])
            if tests != 0:
                raise RuntimeError("archived PR90 control tests failed")
        verify_files(root, info["files"])
        import importlib.metadata
        receipt = {"schema": "PR90-SUBMISSION-RECOMPUTATION/1", "status": "passed",
                   "input_binding_sha256": file_digest(section / "source-records.json"),
                   "completed_cases": 10, "counts": result["counts"],
                   "measurement_source_commit": info["measurement_source_commit"],
                   "export_source_commit": info["export_source_commit"],
                   "original_execution_digest": original, "anonymous_audit_execution_digest": identity,
                   "csv_markdown_byte_exact": True, "json_statistical_fields_equal": True,
                   "json_identity_fields": "anonymous execution digest and temporary audit source hashes",
                   "original_files_unchanged": True, "cryptographic_measurements_executed": 0,
                   "plot_dimensions": sizes, "control_test_exit_code": tests,
                   "recompute_runtime": {"python": platform.python_version(),
                     "matplotlib": importlib.metadata.version("matplotlib"),
                     "numpy": importlib.metadata.version("numpy")},
                   "outputs": {p.name: file_digest(p) for p in sorted(output.iterdir()) if p.is_file()}}
        write_json(output / "recompute-verification.json", receipt)
        print(json.dumps(receipt, ensure_ascii=True))


if __name__ == "__main__":
    main()
