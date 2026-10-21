"""Append pinned PR90 public evidence to a new, anonymous supporting copy."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = "docs/research/2026-10-21-ten-combination-benchmark-results/"
PLAN = "docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json"
SECTION = "07_十组合性能实验"
EXPORT_COMMIT = "8c95cbd398981869ad57a8f38ca639b0940ab230"
MEASURED_COMMIT = "a202c6d3c87798911675b11a46b44903405370df"
BASE_SHA = "1a564faa972aeb483f4f08e70450bc4118c09dce6c999eab859f1975cd05360a"
CODE = ["experiments/research/ten_combination_" + name + ".py"
        for name in ("benchmark", "worker", "summary", "basic_comparison")]
CODE += ["experiments/research/runtime_metrics.py",
         "tests/test_ten_combination_basic_comparison.py", "tests/test_ten_combination_benchmark.py", PLAN]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git_bytes(name):
    return subprocess.check_output(["git", "show", EXPORT_COMMIT + ":" + name], cwd=ROOT)


def anonymous_copy(raw, home):
    changed = []
    if home.encode() in raw:
        raw = raw.replace(home.encode(), b"/home/participant")
        changed.append("participant-home-path-display")
    if raw.lstrip().startswith(b"<?xml") or raw.lstrip().startswith(b"<testsuites"):
        value = re.sub(rb'hostname="[^"]+"', b'hostname="benchmark-host"', raw)
        if value != raw:
            raw = value
            changed.append("test-host-display")
    return raw, changed


def valid_names(names):
    seen = set()
    for name in names:
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                or name.casefold() in seen):
            raise ValueError("invalid or duplicate archive member")
        seen.add(name.casefold())


def stage(args):
    lock = json.loads((HERE / "wheel-lock.json").read_bytes())
    for item in lock["wheels"]:
        if sha256(args.wheels / item["filename"]) != item["sha256"]:
            raise ValueError("offline wheel checksum mismatch")
    if sha256(args.base_zip) != BASE_SHA:
        raise ValueError("base supporting ZIP differs from the verified PR91 delivery")
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("staging output must be empty")
    with zipfile.ZipFile(args.base_zip) as archive:
        valid_names(archive.namelist())
        archive.extractall(args.output)
    section = args.output / SECTION
    section.mkdir()
    environment = json.loads(git_bytes(RESULTS + "calibration-02/environment.json"))
    match = re.match(r"(/home/[^/]+)/", environment["interpreter"])
    if not match:
        raise ValueError("unknown participant-home display format")
    home = match[1]
    files, transforms = {}, []

    def put(source_name, target_name):
        original = git_bytes(source_name)
        raw, changes = anonymous_copy(original, home)
        destination = args.output / target_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != raw:
            raise ValueError("refusing to replace an existing source file: " + target_name)
        destination.write_bytes(raw)
        record = dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), source_path=source_name,
                      source_commit=EXPORT_COMMIT, source_sha256=hashlib.sha256(original).hexdigest(),
                      byte_exact=not changes, transformations=changes)
        files[target_name] = record
        if changes:
            transforms.append(dict(path=target_name, **record))

    for source_name in CODE:
        put(source_name, "01_程序源码/" + source_name)
    put(PLAN, SECTION + "/参数/matrix.json")
    names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", EXPORT_COMMIT,
                                     "--", RESULTS], cwd=ROOT).decode().splitlines()
    for source_name in names:
        relative = source_name.removeprefix(RESULTS)
        if relative.startswith("basic-comparison/"):
            put(source_name, SECTION + "/结果/" + relative.split("/", 1)[1])
        elif relative.startswith(("calibration-02/", "basic-supplement-01/")):
            if not relative.endswith((".json", ".csv")):
                continue
            put(source_name, SECTION + "/数据/" + relative)
        elif relative == "basic-design.json":
            put(source_name, SECTION + "/数据/basic-design.json")
        elif relative in ("validation.json", "final-controls.xml"):
            put(source_name, SECTION + "/验收/PR90-" + relative)
    for source_name, target_name in (("README.md", "README.md"), ("recompute.py", "recompute.py"),
                                     ("recompute.ps1", "复算.ps1"), ("recompute.sh", "复算.sh")):
        raw = (HERE / source_name).read_bytes().replace(b"\r\n", b"\n")
        destination = section / target_name
        destination.write_bytes(raw)
        files[SECTION + "/" + target_name] = dict(sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw), builder_source="deployment/pr90_support/" + source_name)
    wheels = section / "wheels"
    wheels.mkdir()
    for item in lock["wheels"]:
        candidate = args.wheels / item["filename"]
        if sha256(candidate) != item["sha256"]:
            raise ValueError("offline wheel checksum mismatch")
        shutil.copyfile(candidate, wheels / candidate.name)
        files[SECTION + "/wheels/" + candidate.name] = dict(sha256=item["sha256"], bytes=item["bytes"],
            third_party_name=item["name"], version=item["version"], license=item["license"])
    shutil.copyfile(HERE / "wheel-lock.json", section / "wheel-lock.json")
    files[SECTION + "/wheel-lock.json"] = dict(sha256=sha256(section / "wheel-lock.json"))
    info = dict(schema="PR90-SUBMISSION-SOURCES/1", export_source_commit=EXPORT_COMMIT,
                measurement_source_commit=MEASURED_COMMIT, base_supporting_zip_sha256=BASE_SHA,
                participant_home_display="/home/participant",
                original_home_prefix_sha256=hashlib.sha256(home.encode()).hexdigest(), files=files)
    (section / "source-records.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (section / "匿名转换记录.json").write_text(json.dumps(transforms, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in section.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".csv", ".md", ".xml", ".py", ".sh", ".ps1"):
            if home.encode() in path.read_bytes():
                raise ValueError("participant home remains in a submission text")
    readme = args.output / "README.txt"
    readme.write_text("新增十组合材料：进入07_十组合性能实验查看比较表、原始公开收据和离线复算入口。\n\n" + readme.read_text(encoding="utf-8"), encoding="utf-8")
    guide = args.output / "00_材料说明/阅读指引.md"
    guide.write_text(guide.read_text(encoding="utf-8") + "\n\n## 十组合同机基本性能材料\n\n"
        "详见[十组合材料与复算说明](../07_十组合性能实验/README.md)。每组一个独立根，64 B身份、32 B消息；"
        "PR90测量使用Ultra9／Sage10.9，06中的镜像用于演示与收据复算，保持Sage10.7。报告正文尚未写入这批新表。\n", encoding="utf-8")
    rows = [["材料", "提交包路径", "用途", "报告对应"]]
    for name in ("basic-comparison.md", "basic-comparison.csv", "basic-summary.json", "operation-times.png", "object-sizes.png"):
        rows.append(["十组合同机基本比较", SECTION + "/结果/" + name, "原表图与数据", "新增支撑材料；报告正文未改"])
    output = io.StringIO(); csv.writer(output, lineterminator="\n").writerows(rows)
    (args.output / "00_材料说明/新增十组合材料索引.csv").write_text(output.getvalue(), encoding="utf-8")
    print(json.dumps({"stage": str(args.output), "new_files_bound": len(files), "anonymous_display_transforms": len(transforms)}))


def verify_seal_sources(root, info, validation):
    if validation.get("input_binding_sha256") != sha256(root / SECTION / "source-records.json"):
        raise ValueError("validation does not bind the current source records")
    for name, row in info["files"].items():
        if sha256(root / name) != row["sha256"]:
            raise ValueError("bound PR90 input changed after validation: " + name)


def seal(args):
    root = args.stage.resolve()
    manifest_path = root / "文件清单.json"
    manifest = json.loads(manifest_path.read_bytes())
    info = json.loads((root / SECTION / "source-records.json").read_bytes())
    validation_path = root / SECTION / "验收/提交副本复算验证.json"
    validation = json.loads(validation_path.read_bytes())
    if validation["status"] != "passed" or validation["completed_cases"] != 10:
        raise ValueError("successful real recomputation receipt required")
    verify_seal_sources(root, info, validation)
    old = {r["path"]: r for r in manifest["files"]}
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in ("文件清单.json", "SHA256SUMS.txt"):
            continue
        record = dict(old.get(relative, dict(path=relative)))
        value = sha256(path)
        if relative in old and value != old[relative]["sha256"]:
            if relative not in ("README.txt", "00_材料说明/阅读指引.md"):
                raise ValueError("unexpected replacement of original material: " + relative)
            record.update(prior_sha256=old[relative]["sha256"], transformation="PR90 material navigation")
        record.update(info["files"].get(relative, {}))
        record.update(bytes=path.stat().st_size, sha256=value)
        records.append(record)
    manifest.update(files=records, pr90_materials=dict(source_commit=EXPORT_COMMIT,
        measurement_source_commit=MEASURED_COMMIT, base_supporting_zip_sha256=BASE_SHA,
        packager_source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        source_records=SECTION + "/source-records.json", recomputation=SECTION + "/验收/提交副本复算验证.json"))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums = [r["sha256"] + "  " + r["path"] for r in records]
    sums.append(sha256(manifest_path) + "  文件清单.json")
    (root / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(root / "核对文件.py")], check=True)
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix(),
                    compress_type=zipfile.ZIP_STORED if path.name.endswith((".tar.gz", ".whl")) else zipfile.ZIP_DEFLATED)
    if args.output.stat().st_size >= 4_000_000_000:
        raise ValueError("supporting package exceeds 4 GB")
    print(json.dumps(dict(bytes=args.output.stat().st_size, sha256=sha256(args.output), payload_files=len(records))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("stage")
    build.add_argument("--base-zip", type=Path, required=True)
    build.add_argument("--wheels", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    finish = sub.add_parser("seal")
    finish.add_argument("--stage", type=Path, required=True)
    finish.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    (stage if args.command == "stage" else seal)(args)


if __name__ == "__main__":
    main()
