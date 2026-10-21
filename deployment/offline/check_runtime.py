"""Public dependency/source preflight; no setup, keys, or external network access."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.health:
        from urllib.request import urlopen
        with urlopen("http://127.0.0.1:8765/api/jobs", timeout=5) as response:
            assert response.status == 200
        return
    from sage.all import ZZ
    from ibme.assembly import SuiteConfig, validate_suite
    assert ZZ(2) + ZZ(3) == 5
    info = json.loads(Path("/opt/ibme/source-info.json").read_text())
    distribution = importlib.metadata.distribution("ibme")
    for name, expected in info["application_files"].items():
        # experiments is a namespace package and deliberately has no __file__.
        path = Path(distribution.locate_file(name))
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("installed application source mismatch: " + name)
    receipts = json.loads(Path("/opt/ibme/native/build-receipt.json").read_text())
    for record in receipts:
        if hashlib.sha256(Path(record["path"]).read_bytes()).hexdigest() != record["sha256"]:
            raise RuntimeError("native binary checksum mismatch")
        if record["engine"] != "sageloli":
            actual = json.loads(subprocess.check_output([record["path"], "meta"], timeout=30))
            if actual != record["metadata"]:
                raise RuntimeError("native ABI/source fingerprint mismatch")
    from experiments.research.candidates.sageloli.ring.native import Library
    Library("/opt/ibme/native/sageloli/ring.so")
    import ibme.webui.server as web
    suites = []
    for preset in ("primary", "srgg", "ring"):
        config = web._make_config({"preset": preset})
        report = validate_suite(config)
        if not report.ok:
            raise RuntimeError(preset + ": " + "; ".join(report.errors))
        data = config.to_dict()
        assert (data["security_claim"], data["backend_admitted"], data["parameters_are_formal"]) == ("secure", True, True)
        suites.append({"preset": preset, "digest": config.digest, "capacity": report.capacity,
                       "security_claim": data["security_claim"], "backend_admitted": True,
                       "parameters_are_formal": True})
    print(json.dumps({"status": "ok", "application_source_commit": info["application_source_commit"],
                      "python": platform.python_version(), "sage": importlib.metadata.version("sagemath-standard"),
                      "cryptography": importlib.metadata.version("cryptography"),
                      "application_files_verified": len(info["application_files"]),
                      "native_binaries_verified": len(receipts), "suites": suites}, ensure_ascii=False))


if __name__ == "__main__":
    main()
