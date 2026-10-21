"""Compile the correct-base editorial merge with concise figures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "作品设计报告.tex"


def report_inputs() -> list[Path]:
    """Return every literal TeX and image input reachable from the main file."""
    pending = [SOURCE]
    visited: set[Path] = set()
    paths: set[Path] = set()
    while pending:
        path = pending.pop().resolve()
        if path in visited:
            continue
        visited.add(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        paths.add(path)
        if path.suffix != ".tex":
            continue
        contents = path.read_text(encoding="utf-8")
        for name in re.findall(r"\\input\{([^}]+)\}", contents):
            child = (HERE / name)
            if child.suffix == "":
                child = child.with_suffix(".tex")
            pending.append(child)
        for name in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", contents):
            pending.append(HERE / name)
    return sorted(paths)


def input_digests() -> dict[str, str]:
    return {
        Path(os.path.relpath(path, HERE)).as_posix():
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in report_inputs()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", help="path/name of tectonic, latexmk, or xelatex")
    args = parser.parse_args()
    engine = args.engine or next(
        (
            path
            for name in ("tectonic", "latexmk", "xelatex")
            if (path := shutil.which(name))
        ),
        None,
    )
    if engine is None:
        parser.error("install Tectonic or XeLaTeX/latexmk, or supply --engine")
    engine = shutil.which(engine) or str(Path(engine).expanduser().resolve())
    name = Path(engine).stem.lower()

    source_digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    inputs = input_digests()
    with tempfile.TemporaryDirectory(prefix="ibme-report-correct-base-") as build:
        if name == "tectonic":
            command = [engine, "--untrusted", "--keep-logs", "--keep-intermediates", "--outdir", build, SOURCE.name]
            passes = 1
        elif name == "latexmk":
            command = [
                engine,
                "-xelatex",
                "-halt-on-error",
                "-interaction=nonstopmode",
                "-outdir=" + build,
                SOURCE.name,
            ]
            passes = 1
        elif name == "xelatex":
            command = [
                engine,
                "-halt-on-error",
                "-interaction=nonstopmode",
                "-output-directory=" + build,
                SOURCE.name,
            ]
            passes = 3
        else:
            parser.error("supported engine names: tectonic, latexmk, xelatex")

        for _ in range(passes):
            result = subprocess.run(command, cwd=HERE, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace")
            if result.returncode:
                print((result.stdout + result.stderr)[-8000:])
                result.check_returncode()
        built_pdf = Path(build) / SOURCE.with_suffix(".pdf").name
        if not built_pdf.is_file() or not built_pdf.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("engine did not produce a valid PDF")
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_digest:
            raise RuntimeError("LaTeX source changed during compilation")
        if input_digests() != inputs:
            raise RuntimeError("included report inputs changed during compilation")
        target = SOURCE.with_suffix(".pdf")
        shutil.copyfile(built_pdf, target)
        manifest = {
            "schema": "IBME-COMPETITION-REPORT-BUILD/1",
            "source": SOURCE.name,
            "source_sha256": source_digest,
            "pdf": target.name,
            "pdf_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "engine": name,
            "inputs": inputs,
        }
        (HERE / "build-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        log = Path(build) / SOURCE.with_suffix(".log").name
        if log.is_file():
            contents = log.read_text(encoding="utf-8", errors="replace")
            (HERE / "build.log").write_text(
                "\n".join(line.rstrip() for line in contents.splitlines()) + "\n",
                encoding="utf-8", newline="\n")
        aux = Path(build) / SOURCE.with_suffix(".aux").name
        if aux.is_file():
            labels = re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}\{([^}]+)\}",
                                aux.read_text(encoding="utf-8", errors="replace"))
            (HERE / "cross-references.json").write_text(
                json.dumps({key:{"number":number,"page":page} for key,number,page in labels},
                           ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
