"""Actual Web acceptance in a running container; only public summaries are saved.

Example inside a --network none container: python verify_web.py --presets primary srgg ring.
This checks deployment functionality, not comparative performance.
"""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen


def request(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    with urlopen(Request(base + path, data=data, headers={"Content-Type": "application/json"}), timeout=10) as response:
        return json.load(response)


def operation(base, name, payload):
    submitted = request(base, "/api/jobs", {"operation": name, "payload": payload})
    job = submitted["job"]
    identifier = job["id"]
    deadline = time.monotonic() + 3600
    previous = None
    while True:
        job = request(base, "/api/jobs")["job"]
        if job["id"] != identifier:
            raise RuntimeError("another client replaced the acceptance job")
        status = (job["status"], job.get("phase"))
        if status != previous:
            print(json.dumps({"operation": name, "status": status}, ensure_ascii=False), flush=True)
            previous = status
        if job["status"] == "failed":
            raise RuntimeError(job["error"])
        if job["status"] == "completed":
            result = job["result"]
            if not result.get("ok", False):
                raise RuntimeError("operation returned a failed result")
            return result
        if time.monotonic() > deadline:
            raise RuntimeError("acceptance operation timed out")
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--presets", nargs="+", choices=("primary", "srgg", "ring"), default=["primary", "srgg"])
    parser.add_argument("--output", type=Path, default=Path("/tmp/web-acceptance.json"))
    args = parser.parse_args()
    results = []
    for preset in args.presets:
        operation(args.base, "reset", {})
        checked = operation(args.base, "check", {"preset": preset})
        prepared = operation(args.base, "bootstrap", {"preset": preset, "sender": "Alice", "receiver": "Bob", "wrong_receiver": "Carol"})
        message = "Offline IBME acceptance message!"
        assert len(message.encode()) == 32
        encrypted = operation(args.base, "encrypt", {"message": message})
        modes = ("normal",) if preset == "ring" else ("normal", "wrong_sender", "wrong_receiver", "both_wrong", "tamper", "truncate")
        observations = []
        for mode in modes:
            result = operation(args.base, "decrypt", {"mode": mode})
            assert result["expectation_met"] is True
            assert result["bottom"] is (mode != "normal")
            if mode == "normal":
                assert result["message"] == message
            observations.append({k: result[k] for k in ("mode", "bottom", "expectation_met", "seconds")})
        results.append({"preset": preset, "suite_digest": checked["suite"]["digest"],
                        "suite": checked["suite_config"], "message_bytes": 32,
                        "prepare_events": prepared["events"], "ciphertext": encrypted["ciphertext"],
                        "observations": observations})
        args.output.write_text(json.dumps({"scope": "deployment acceptance; one root per preset; no performance ranking", "results": results}, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"preset": preset, "accepted": True, "cases": len(observations)}), flush=True)
    operation(args.base, "reset", {})


if __name__ == "__main__":
    main()
