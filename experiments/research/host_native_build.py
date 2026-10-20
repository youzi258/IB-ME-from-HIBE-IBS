"""Build pinned native engines with dependencies supplied by the host shell.

The historical builders intentionally target a Sage/conda prefix.  This
companion is for environments such as NixOS, where the compiler wrapper
already carries the required include, library and runtime-search flags.  It
does not discover or persist host dependency paths.  The resulting engines
still expose, and are checked against, the existing source identifiers.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def compiler(name, default):
    value = os.environ.get(name, default)
    require(value and not any(character.isspace() for character in value),
            f"{name} must name one compiler executable without arguments")
    return value


def compiler_version(executable):
    result = subprocess.run([executable, "--version"], capture_output=True,
                            text=True, timeout=30, check=True)
    require(bool(result.stdout.splitlines()), "compiler version output missing")
    return result.stdout.splitlines()[0]


def run_compile(command, log, timeout, *, allow_native_isa=False):
    environment = None
    if allow_native_isa and "NIX_ENFORCE_NO_NATIVE" in os.environ:
        environment = dict(os.environ)
        environment.pop("NIX_ENFORCE_NO_NATIVE")
    result = subprocess.run(command, capture_output=True, timeout=timeout,
                            env=environment)
    if result.returncode:
        log.write_bytes(result.stderr)
        raise RuntimeError(f"native compilation failed; diagnostics retained at {log}")


def latte_command(build, output, fingerprint, executable="gcc"):
    sources = [str(path) for path in sorted(build.glob("*.c"))
               if path.name not in ("test.c", "randombytes.c", "cpucycles.c")]
    return [
        executable, "-O2", "-march=native", "-fwrapv", "-include", "string.h",
        "-I" + str(build), "-I" + str(build / "compat"),
        f'-DIBME_LATTE_SOURCE_ID="{fingerprint}"', *sources,
        "-lgmp", "-lmpfr", "-lmpc", "-lcrypto", "-lquadmath", "-o", str(output),
    ]


def build_latte(directory):
    from ibme.hibe.latte.native import build as original

    require(os.name == "posix", "host native builds require POSIX")
    directory.mkdir(parents=True, exist_ok=False)
    fingerprint = original.source_id()
    cc = compiler("CC", "gcc")
    with tempfile.TemporaryDirectory(prefix="latte-host-build-", dir=directory) as temporary:
        build = Path(temporary)
        for path in (original.HERE / "upstream").iterdir():
            if path.suffix in (".c", ".h"):
                (build / path.name).write_text(
                    original.patched(path.name, path.read_text()), encoding="utf-8")
        shutil.copytree(original.HERE / "compat", build / "compat")
        for name in ("bridge.c", "shake.c"):
            shutil.copyfile(original.HERE / name, build / name)
        compiled = build / "ibme-latte3"
        command = latte_command(build, compiled, fingerprint, cc)
        run_compile(command, directory / "compiler-error.log", 180,
                    allow_native_isa=True)
        destination = directory / "bin" / "ibme-latte3"
        destination.parent.mkdir()
        shutil.copyfile(compiled, destination)
        destination.chmod(0o700)
    metadata = json.loads(subprocess.run(
        [str(destination), "meta"], input=b"", capture_output=True,
        timeout=30, check=True).stdout)
    expected = {"abi": "IBME-LATTE3-COEFF-1", "source_id": fingerprint,
                "n": 1024, "q": 68718428161}
    require(metadata == expected, "LATTE host build ABI/source mismatch")
    return {
        "engine": "latte", "status": "built", "source_id": fingerprint,
        "binary_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "executable": str(destination), "metadata": metadata,
        "compiler": compiler_version(cc), "dependency_mode": "host-toolchain",
        "flags": ["-O2", "-march=native", "-fwrapv"],
        "nix_native_isa_guard_removed_for_compile": "NIX_ENFORCE_NO_NATIVE" in os.environ,
        "scope": "build provenance; not a security evaluation",
    }


def sageloli_command(source, output, fingerprint, executable="g++"):
    return [
        executable, "-O3", "-std=c++17", "-fPIC", "-shared", "-fopenmp",
        f'-DSG_SOURCE_ID="{fingerprint}"', str(source),
        "-lflint", "-lgmp", "-o", str(output),
    ]


def build_sageloli(directory):
    from experiments.research.candidates.sageloli.ring import native

    require(os.name == "posix", "host native builds require POSIX")
    directory.mkdir(parents=True, exist_ok=False)
    fingerprint = native.source_id()
    cxx = compiler("CXX", "g++")
    destination = native.build(directory, dependency_mode="host-toolchain")
    metadata = native.Library(destination).metadata()
    require(metadata["source_id"] == fingerprint, "Sageloli host build source mismatch")
    return {
        "engine": "sageloli", "status": "built", "source_id": fingerprint,
        "binary_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "library": str(destination), "metadata": metadata,
        "compiler": compiler_version(cxx), "dependency_mode": "host-toolchain",
        "flags": ["-O3", "-std=c++17", "-fPIC", "-shared", "-fopenmp"],
        "scope": "build provenance; not a security evaluation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("latte", "sageloli"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    builders = {"latte": build_latte, "sageloli": build_sageloli}
    result = builders[args.engine](args.directory.resolve())
    (args.directory / "build.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
