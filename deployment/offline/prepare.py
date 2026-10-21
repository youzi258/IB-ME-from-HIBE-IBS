"""Prepare an allowlisted Docker context; never send the working tree to Docker."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
APPROVED_LICENSES = {
    "4c0836c695ab4bc4a0ec262bbae2a75f7f6295ef3d3882ae52fd777e70b0984d",
    "20367e8b5d0f661448fbe668c15faec4a432fc01e0cc671641509d0a06f4e6d3",
}
NOTICE = "Copyright (c) 2026 作品 CACR2026T4PMR7 著作权人".encode()
FILES = ("Dockerfile", "environment-linux-64.lock", "environment-sources.json",
         "python-runtime.lock", "build_native.py", "check_runtime.py", "collect_licenses.py",
         "entrypoint.sh", "source-info.json")


def digest(path, algorithm="sha256"):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def license_body(raw):
    return re.sub(rb"(?m)^Copyright \(c\)[^\r\n]*", b"", raw)


def anonymize_wheel(source, target):
    """Only the project's explicitly approved MIT notice and RECORD may change."""
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        seen = set()
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if (not name or "\\" in name or path.is_absolute() or ":" in name
                    or ".." in path.parts or name.casefold() in seen):
                raise ValueError("invalid or duplicate wheel member")
            seen.add(name.casefold())
        data = {info.filename: archive.read(info) for info in infos}
    license_names = [n for n in data if re.fullmatch(r"ibme-[^/]+\.dist-info/licenses/LICENSE", n)]
    if len(license_names) != 1:
        raise ValueError("missing approved project license")
    name = license_names[0]
    if hashlib.sha256(data[name].replace(b"\r\n", b"\n")).hexdigest() not in APPROVED_LICENSES:
        raise ValueError("wheel does not contain the approved project license")
    data[name] = re.sub(rb"(?m)^Copyright \(c\)[^\r\n]*", NOTICE, data[name], count=1)
    records = [n for n in data if re.fullmatch(r"ibme-[^/]+\.dist-info/RECORD", n)]
    if len(records) != 1:
        raise ValueError("missing wheel RECORD")
    record = records[0]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for name, raw in data.items():
        if name == record:
            writer.writerow((name, "", ""))
        else:
            value = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
            writer.writerow((name, "sha256=" + value, len(raw)))
    data[record] = output.getvalue().encode()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for info in infos:
            archive.writestr(info, data[info.filename])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True,
                        help="directory containing the wheel pinned by python-runtime.lock")
    parser.add_argument("--conda-cache", type=Path)
    args = parser.parse_args()
    # Refuse a populated destination: no accidental files can enter the context.
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("output must be empty")
    wheel = args.output / "ibme-0.1.0-py3-none-any.whl"
    anonymize_wheel(args.wheel, wheel)
    for name in FILES:
        raw = (HERE / name).read_bytes()
        if name.endswith(".sh"):
            raw = raw.replace(b"\r\n", b"\n")
        (args.output / name).write_bytes(raw)
    source = json.loads((HERE / "source-info.json").read_text(encoding="utf-8"))
    # Check logical contents rather than wheel ZIP compression/timestamps.
    with zipfile.ZipFile(wheel) as archive:
        for name, expected in source["application_files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError("application wheel differs from frozen source: " + name)
        actual = {n for n in archive.namelist() if n.startswith(("ibme/", "experiments/"))}
        if actual != set(source["application_files"]):
            raise ValueError("unexpected application wheel payload")
    wheelhouse = args.output / "wheelhouse"
    wheelhouse.mkdir()
    # The release has exactly one external Python wheel; reject substitutions.
    expected_wheel = source["cryptography_wheel"]
    candidate = args.wheelhouse / expected_wheel["filename"]
    if digest(candidate) != expected_wheel["sha256"]:
        raise ValueError("cryptography wheel checksum mismatch")
    shutil.copyfile(candidate, wheelhouse / candidate.name)
    cache = args.output / "conda-cache"
    cache.mkdir()
    if args.conda_cache:
        packages = json.loads((HERE / "environment-sources.json").read_text())["packages"]
        for package in packages:
            candidate = args.conda_cache / package["fn"]
            if candidate.is_file():
                if digest(candidate) != package["sha256"]:
                    raise ValueError("conda cache checksum mismatch: " + candidate.name)
                shutil.copyfile(candidate, cache / candidate.name)
    print(json.dumps({"context": str(args.output), "wheel_sha256": digest(wheel),
                      "cached_conda_packages": len(list(cache.iterdir()))}))


if __name__ == "__main__":
    main()
