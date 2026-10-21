"""Add a verified offline release to a NEW copy of the supporting ZIP."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-zip", type=Path, required=True)
    parser.add_argument("--offline-release", type=Path, required=True)
    parser.add_argument("--recipe-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite an existing ZIP")
    runtime = json.loads((args.offline_release / "runtime-image.json").read_text())
    archive = args.offline_release / runtime["archive"]
    if archive.parent.resolve() != args.offline_release.resolve() or sha256(archive) != runtime["sha256"]:
        raise ValueError("offline image archive checksum/path mismatch")
    with tempfile.TemporaryDirectory(prefix="supporting-with-runtime-", dir=args.output.parent) as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(args.base_zip) as source:
            seen = set()
            for name in source.namelist():
                parts = PurePosixPath(name)
                if parts.is_absolute() or ".." in parts.parts or "\\" in name or name.casefold() in seen:
                    raise ValueError("invalid base ZIP entry")
                seen.add(name.casefold())
            source.extractall(root)
        manifest = json.loads((root / "文件清单.json").read_text(encoding="utf-8"))
        subprocess.run([sys.executable, str(root / "核对文件.py")], check=True)
        old_records = {r["path"]: r for r in manifest["files"]}
        destination = root / "06_离线运行环境"
        shutil.copytree(args.offline_release, destination)
        shutil.copyfile(HERE / "verify_supporting.py", root / "核对文件.py")
        readme = root / "README.txt"
        old_readme = readme.read_text(encoding="utf-8").replace(
            "本包不含Sage等运行环境，依赖安装步骤见运行与演示.md。",
            "本包的06_离线运行环境已含Sage等运行依赖；手动重建仍可参考运行与演示.md。")
        readme.write_text("离线启动：先进入 06_离线运行环境，Windows 运行 start.ps1，Linux 运行 sh start.sh。\n"
                          "完整说明和镜像 SHA-256 位于该目录；A/B/C演示无需重新安装 Sage 或编译原生库。\n\n" + old_readme, encoding="utf-8")
        guide = root / "00_材料说明/阅读指引.md"
        guide.write_text(guide.read_text(encoding="utf-8") + "\n\n## 离线运行补充\n\n"
                         "优先使用 [离线运行环境](../06_离线运行环境/README.md)。原使用说明 PDF 和手工安装说明继续保留，供源码重建参考；"
                         "本次新增镜像固定原包源码与参数，未更改作品报告和历史实验数据。部署验收记录位于离线环境目录。\n", encoding="utf-8")
        manifest.update({"offline_runtime": runtime, "container_recipe_commit": args.recipe_commit,
                         "base_supporting_zip_sha256": sha256(args.base_zip)})
        records = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            name = path.relative_to(root).as_posix()
            if name in ("文件清单.json", "SHA256SUMS.txt"):
                continue
            record = dict(old_records.get(name, {"path": name, "transformation": "offline deployment addition"}))
            value = sha256(path)
            if name in old_records and value != record["sha256"]:
                record["prior_sha256"] = record["sha256"]
                record["transformation"] = "offline deployment navigation or streaming verifier; original source/data unchanged"
            record.update({"bytes": path.stat().st_size, "sha256": value})
            records.append(record)
        manifest["files"] = records
        (root / "文件清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = [r["sha256"] + "  " + r["path"] for r in records]
        lines.append(sha256(root / "文件清单.json") + "  文件清单.json")
        (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run([sys.executable, str(root / "核对文件.py")], check=True)
        with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as output:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(root).as_posix(),
                                 compress_type=zipfile.ZIP_STORED if path.name.endswith(".tar.gz") else zipfile.ZIP_DEFLATED)
        if args.output.stat().st_size >= 4_000_000_000:
            raise RuntimeError("supporting ZIP exceeds 4 GB; do not upload")
    print(json.dumps({"zip": str(args.output), "bytes": args.output.stat().st_size,
                      "sha256": sha256(args.output), "payload_files": len(records)}))


if __name__ == "__main__":
    main()
