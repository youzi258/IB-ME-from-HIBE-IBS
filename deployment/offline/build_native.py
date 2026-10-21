"""Build original fingerprinted bridges with a fixed CPU target inside the image."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def portable_latte_command(build_dir, output, fingerprint, sage_prefix):
    build, sage = Path(build_dir), Path(sage_prefix)
    sources = [str(p) for p in sorted(build.glob("*.c"))
               if p.name not in ("test.c", "randombytes.c", "cpucycles.c")]
    return ["gcc", "-O2", "-march=x86-64-v3", "-mtune=generic", "-maes", "-fwrapv",
            "-include", "string.h", "-I" + str(build), "-I" + str(build / "compat"),
            "-I" + str(sage / "include"), '-DIBME_LATTE_SOURCE_ID="' + fingerprint + '"',
            *sources, "-L" + str(sage / "lib"), "-Wl,-rpath," + str(sage / "lib"),
            "-lgmp", "-lmpfr", "-lmpc", "-lcrypto", "-lquadmath", "-o", str(output)]


def main():
    from ibme.hibe.latte.native import build as latte
    from experiments.research.candidates.sageloli.ring import native as sageloli
    root = Path("/opt/ibme/native")
    root.mkdir(parents=True, exist_ok=True)
    sage = Path("/opt/sage")
    fingerprint = latte.source_id()
    binary = root / "latte/bin/ibme-latte3"
    binary.parent.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="latte-") as temp:
        build = Path(temp)
        for path in (latte.HERE / "upstream").iterdir():
            if path.suffix in (".c", ".h"):
                (build / path.name).write_text(latte.patched(path.name, path.read_text()))
        shutil.copytree(latte.HERE / "compat", build / "compat")
        for name in ("bridge.c", "shake.c"):
            shutil.copyfile(latte.HERE / name, build / name)
        subprocess.run(portable_latte_command(build, binary, fingerprint, sage), check=True, timeout=180)
    binary.chmod(0o755)
    metadata = json.loads(subprocess.check_output([str(binary), "meta"], timeout=30))
    assert metadata == {"abi": "IBME-LATTE3-COEFF-1", "source_id": fingerprint,
                        "n": 1024, "q": 68718428161}
    records = [{"engine": "latte", "metadata": metadata, "path": str(binary),
                "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "flags": ["-O2", "-march=x86-64-v3", "-mtune=generic", "-maes", "-fwrapv"]}]
    for module, directory in (("ibme.ibs.certified.native.build", "mldsa"),
                              ("ibme.ibs.certified.falcon_native.build", "falcon")):
        subprocess.run([sys.executable, "-m", module, "--prefix", str(root / directory)],
                       check=True, timeout=600)
        for path in (root / directory / "bin").iterdir():
            path.chmod(0o755)
            records.append({"engine": directory, "path": str(path),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "metadata": json.loads(subprocess.check_output([str(path), "meta"]))})
    library = sageloli.build(root / "sageloli", dependency_mode="sage-prefix")
    shutil.copyfile(library, root / "sageloli/ring.so")
    records.append({"engine": "sageloli", "path": str(root / "sageloli/ring.so"),
                    "sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                    "metadata": sageloli.Library(library).metadata()})
    (root / "build-receipt.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps({"native_engines_built": len(records)}))


if __name__ == "__main__":
    main()
