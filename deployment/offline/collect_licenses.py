"""Retain conda license texts and upstream recipe metadata before cache cleanup."""
import json
from pathlib import Path
import shutil


def main():
    source = json.loads(Path("/tmp/environment-sources.json").read_text())
    output = Path("/opt/ibme/licenses/conda")
    output.mkdir(parents=True)
    for package in source["packages"]:
        filename = package["fn"]
        name = filename.removesuffix(".conda").removesuffix(".tar.bz2")
        info = Path("/opt/conda/pkgs") / name / "info"
        if not info.is_dir():
            raise RuntimeError("extracted package metadata missing: " + name)
        target = output / name
        target.mkdir()
        for item in ("licenses", "recipe", "about.json", "index.json", "hash_input.json"):
            path = info / item
            if path.is_dir():
                shutil.copytree(path, target / item, symlinks=False)
            elif path.is_file():
                shutil.copyfile(path, target / item)
    shutil.copyfile("/tmp/environment-sources.json", output / "environment-sources.json")
    print(json.dumps({"conda_package_notices_collected": len(source["packages"])}))


if __name__ == "__main__":
    main()
