"""Stream docker save through gzip, then write offline launch metadata."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--image", default="cacr2026t4pmr7/ibme:2026-10-21")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    image = json.loads(subprocess.check_output([args.docker, "image", "inspect", args.image]))[0]
    if (image["Os"], image["Architecture"]) != ("linux", "amd64"):
        raise RuntimeError("expected linux/amd64 image")
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / "CACR2026T4PMR7-ibme-linux-amd64.tar.gz"
    if destination.exists():
        raise RuntimeError("refusing to overwrite existing image archive")
    temporary = destination.with_suffix(".partial")
    try:
        with temporary.open("xb") as raw:
            process = subprocess.Popen([args.docker, "image", "save", args.image], stdout=subprocess.PIPE)
            try:
                with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=6) as compressed:
                    shutil.copyfileobj(process.stdout, compressed, 4 * 1024 * 1024)
                code = process.wait()
                if code:
                    raise RuntimeError("docker save failed")
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()
        if temporary.stat().st_size >= 4_000_000_000:
            raise RuntimeError("compressed image exceeds competition supporting-material size limit")
        temporary.rename(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    manifest = {"schema": "IBME-OFFLINE-IMAGE/1", "image_id": image["Id"], "tag": args.image,
                "os": image["Os"], "architecture": image["Architecture"],
                "minimum_cpu": "x86-64-v3 with AES-NI", "archive": destination.name,
                "bytes": destination.stat().st_size, "sha256": sha256(destination),
                "application_source_commit": json.loads((HERE / "source-info.json").read_text())["application_source_commit"],
                "recipe_files": {p.name: sha256(p) for p in sorted(HERE.iterdir()) if p.is_file()
                                 and p.name not in ("runtime-image.json", "IMAGE_ID", "IMAGE_ARCHIVE", "IMAGE_SHA256SUMS.txt")}}
    (args.output / "runtime-image.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (args.output / "IMAGE_ID").write_text(image["Id"] + "\n", encoding="ascii", newline="\n")
    (args.output / "IMAGE_ARCHIVE").write_text(destination.name + "\n", encoding="ascii", newline="\n")
    (args.output / "IMAGE_SHA256SUMS.txt").write_text(manifest["sha256"] + "  " + destination.name + "\n", encoding="ascii", newline="\n")
    for name in ("start.ps1", "start.sh", "README.md"):
        (args.output / name).write_bytes((HERE / name).read_bytes().replace(b"\r\n", b"\n"))
    recipe = args.output / "build"
    recipe.mkdir(exist_ok=True)
    for path in HERE.iterdir():
        if path.is_file():
            shutil.copyfile(path, recipe / path.name)
    print(json.dumps({k: v for k, v in manifest.items() if k != "recipe_files"}))


if __name__ == "__main__":
    main()
