"""Combine the declared single-root batches without changing original receipts."""
from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
import shutil
import tempfile

from .ten_combination_benchmark import digest, file_digest, stable_identity, write_json
from .ten_combination_summary import OPERATIONS, export_summary, plots


def read_verified(public):
    """Recompute from a public-only temporary copy; leave source files untouched."""
    public = Path(public)
    with tempfile.TemporaryDirectory(prefix="ibme-basic-public-") as directory:
        target = Path(directory)
        checksums = {}
        paths = [public / "batch-manifest.json", public / "environment.json"]
        paths.extend(sorted((public / "jobs").glob("*.json")))
        for path in paths:
            if path.is_symlink() or not path.is_file():
                raise ValueError("regular public receipt files required")
            relative = path.relative_to(public)
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target / relative)
            checksums[relative.as_posix()] = file_digest(target / relative)
        result = export_summary(target)
        manifest = json.loads((target / "batch-manifest.json").read_bytes())
        environment = json.loads((target / "environment.json").read_bytes())
    return result, manifest, environment, checksums


def combine(design, sources):
    if design["schema"] != "TEN-COMBINATION-BASIC-DESIGN/1":
        raise ValueError("unknown basic design")
    groups = {design["reused_batch"]: set(design["reused_cases"]),
              design["supplemental_batch"]: set(design["supplemental_cases"])}
    if (len(groups) != 2 or groups[design["reused_batch"]] & groups[design["supplemental_batch"]]
            or sum(map(len, groups.values())) != 10 or set(sources) != set(groups)):
        raise ValueError("the ten cases must have exactly one declared source")
    cases, counts, provenance, failures = {}, {}, {}, []
    identity = None
    for name, (summary, manifest, environment, checksums) in sources.items():
        binding = manifest["binding"]
        if (binding["roots"], binding["warm_repetitions"], binding["restore_repetitions"]) != (1, 1, 1):
            raise ValueError("basic comparison requires one root, one repeat and one recovery")
        if (set(binding["cases"]) != groups[name] or set(summary["cases"]) != groups[name]
                or binding["execution_digest"] != design["execution_digest"]
                or summary["execution_digest"] != design["execution_digest"]
                or digest(stable_identity(environment)) != design["execution_digest"]
                or environment["source_commit"] != design["source_commit"]
                or binding["plan_digest"] != design["plan_digest"]
                or digest(manifest["plan"]) != design["plan_digest"]):
            raise ValueError("batch differs from the declared cases or frozen execution")
        current = stable_identity(environment)
        if identity is not None and current != identity:
            raise ValueError("sources use different environments or measured code")
        identity = current
        for case, record in summary["cases"].items():
            if record["planned_roots"] != 1 or record["passed_roots"] not in (0, 1):
                raise ValueError("invalid independent-root count")
            reference = next(row for row in manifest["plan"]["cases"] if row["name"] == case)
            if record["suite"] != reference["suite"] or record["suite_digest"] != reference["suite_digest"]:
                raise ValueError("case Suite differs from fixed plan")
            cases[case] = dict(copy.deepcopy(record), source_batch=name)
        for key, count in summary["counts"].items():
            counts[key] = counts.get(key, 0) + count
        failures.extend(dict(row, source_batch=name) for row in summary["failures"])
        provenance[name] = dict(original_calibration_flag=binding["calibration"],
                                 source_files=checksums, batch_id=binding["batch_id"])
    completed = sum(row["passed_roots"] for row in cases.values())
    if completed == 10 and counts != design["expected_counts"]:
        raise ValueError("completed basic comparison has incorrect operation counts")
    cases = {row["name"]: cases[row["name"]] for row in manifest["plan"]["cases"]}
    return dict(schema="TEN-COMBINATION-BASIC-COMPARISON/1", status="passed" if completed == 10 else "partial",
                source_commit=design["source_commit"], execution_digest=design["execution_digest"],
                planned_cases=10, completed_cases=completed, roots_per_case=1,
                warm_repetitions=1, restore_repetitions=1,
                identity_bytes=64, message_bytes=32, cases=cases, counts=counts, failures=failures,
                sources=provenance, design=design,
                scope="fixed-configuration basic performance; one first pair, one repeat pair, one restored decrypt")


def write_comparison(output, result):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "basic-summary.json", result)
    rows = []
    for name, case in result["cases"].items():
        row = dict(case=name, hibe=case["suite"]["hibe"], ibs=case["suite"]["ibs"],
                   passed_roots=case["passed_roots"], source_batch=case["source_batch"])
        row.update({operation + "_seconds": case["operations"][operation]["median"] for operation in OPERATIONS})
        row.update({key.removesuffix(".bin") + "_bytes": value["median"] for key, value in case["sizes"].items()})
        rows.append(row)
    with (output / "basic-comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# 十组同机基本性能比较", "", f"已完成 {result['completed_cases']}/10 组。每组1个独立根，64 B身份、32 B消息。",
             "", "| 组合 | 建立/s | 发发送钥/s | 发接收钥/s | 首次加密/s | 首次解密/s | 重复加密/s | 重复解密/s | 恢复后解密/s |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    display = [operation for operation in OPERATIONS if operation != "restore-objects"]
    def format_number(value):
        return "—" if value is None else f"{value:.3g}"
    for name, case in result["cases"].items():
        values = [format_number(case["operations"][operation]["median"]) for operation in display]
        lines.append("| " + " | ".join([name] + values) + " |")
    lines += ["", "| 组合 | 公钥/KiB | 主密钥/KiB | 发送钥/KiB | 接收钥/KiB | 完整密文/KiB |",
              "|---|---:|---:|---:|---:|---:|"]
    for name, case in result["cases"].items():
        values = [format_number(case["sizes"][key]["median"] / 1024) if case["sizes"][key]["median"] is not None else "—"
                  for key in ("public.bin", "master.bin", "sender.bin", "receiver.bin", "ciphertext.bin")]
        lines.append("| " + " | ".join([name] + values) + " |")
    lines += ["", "三组复用已完成的同口径单根记录，七组另批补测；原始收据和原有标签保留。",
              "Lai每次完整解密包含真实委派；LATTE恢复使用既有持久缓存。算法、参数、测量源码及运行环境相同。",
              "额外完成的多次Lai＋Luo试验单独保存，不混入这张单次比较表。", ""]
    (output / "basic-comparison.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--reused-public", type=Path, required=True)
    parser.add_argument("--supplemental-public", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    design = json.loads(args.design.read_bytes())
    sources = {design["reused_batch"]: read_verified(args.reused_public),
               design["supplemental_batch"]: read_verified(args.supplemental_public)}
    result = combine(design, sources)
    write_comparison(args.output, result)
    if args.plots:
        plots(args.output, result)
    print(json.dumps(dict(status=result["status"], completed_cases=result["completed_cases"], counts=result["counts"])))


if __name__ == "__main__":
    main()
