"""Build the review copy's tables and figures from existing public measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCES = {
    "master": "docs/deliveries/2026-10-19-report-experiment-supplement/master-table.json",
    "optimization": "docs/research/2026-10-20-multi-backend-optimization/verified-summary.json",
    "codec": "docs/research/team-b-delivery/2026-10-18-srgg-compact-benchmark/wire.csv",
    "codec_benchmark": "docs/research/team-b-delivery/2026-10-18-srgg-compact-benchmark/benchmark.json",
    "placement": "docs/research/2026-10-19-full-system-placement/evidence/placement.json",
    "combinations": "docs/research/2026-10-20-combination-data-inventory/inventory.json",
    "sageloli_I": "docs/research/team-b-delivery/2026-10-19-sageloli-ring-target/evidence/param-I-fresh.json",
    "sageloli_II": "docs/research/team-b-delivery/2026-10-19-sageloli-ring-target/evidence/param-II-fresh.json",
    "nixos_C": "docs/deliveries/2026-10-20-nixos-independent-reproduction/C.json",
    "nixos_environment": "docs/deliveries/2026-10-20-nixos-independent-reproduction/environment.json",
    "web_A": "docs/deliveries/2026-10-20-web-redesign/A.json",
    "web_B": "docs/deliveries/2026-10-20-web-redesign/B.json",
    "ten_combinations": "docs/research/2026-10-21-ten-combination-benchmark-results/basic-comparison/basic-comparison.csv",
    "ten_design": "docs/research/2026-10-21-ten-combination-benchmark-results/basic-design.json",
    "ten_environment": "docs/research/2026-10-21-ten-combination-benchmark-results/basic-supplement-01/environment.json",
    "ten_validation": "docs/research/2026-10-21-ten-combination-benchmark-results/validation.json",
}
OPERATIONS = [
    ("系统建立", "setup"), ("发送者发钥", "sender-key"),
    ("接收者发钥", "receiver-key"), ("首次加密", "cold-encrypt"),
    ("首次解密", "first-decrypt-with-leaf-generation"),
    ("重复加密", "warm-encrypt"), ("重复解密", "warm-decrypt"),
    ("对象恢复", "restore-objects"), ("恢复后解密", "restored-decrypt"),
]
COMBINATION_ORDER = [
    "latte-mldsa44", "latte-falcon512", "latte-luo-compact",
    "latte-srgg-I-compact", "latte-sageloli-I", "lai-c2-mldsa44",
    "lai-c2-falcon512", "lai-c2-luo-compact", "lai-c2-srgg-I-compact",
    "lai-c2-sageloli-I",
]
COMBINATION_LABELS = {
    "latte-mldsa44": "LATTE＋ML-DSA",
    "latte-falcon512": "LATTE＋Falcon",
    "latte-luo-compact": "LATTE＋Luo",
    "latte-srgg-I-compact": "LATTE＋SRGG",
    "latte-sageloli-I": "LATTE＋Sageloli",
    "lai-c2-mldsa44": "Lai＋ML-DSA",
    "lai-c2-falcon512": "Lai＋Falcon",
    "lai-c2-luo-compact": "Lai＋Luo",
    "lai-c2-srgg-I-compact": "Lai＋SRGG",
    "lai-c2-sageloli-I": "Lai＋Sageloli",
}
REPRESENTATIVE_CASES = {
    "A": "latte-mldsa44",
    "B": "latte-srgg-I-compact",
    "C": "lai-c2-sageloli-I",
}


def load_materials() -> dict:
    data = {}
    for key, relative in SOURCES.items():
        path = ROOT / relative
        if path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as stream:
                data[key] = list(csv.DictReader(stream))
        else:
            data[key] = json.loads(path.read_text(encoding="utf-8"))
    return data


def number(value: float) -> str:
    return f"{value:.3g}"


def duration(value: float) -> str:
    if value < 1:
        return f"{value * 1000:.3g}~ms"
    return f"{value:.3g}~s"


def binary_size(value: float) -> str:
    if value >= 1024**2:
        return f"{value / 1024**2:.3g}~MiB"
    return f"{value / 1024:.3g}~KiB"


def ordered_combinations(data: dict) -> list[dict]:
    rows = {row["case"]: row for row in data["ten_combinations"]}
    missing = set(COMBINATION_ORDER) - rows.keys()
    if missing:
        raise ValueError(f"ten-combination table is missing: {sorted(missing)}")
    return [rows[name] for name in COMBINATION_ORDER]


def frame_accounting(master: dict) -> dict:
    """Count real serializer bytes; recover capsule length by subtraction.

    The dummy objects are only format probes. They are never treated as
    encryption outputs and no cryptographic experiment or private state is used.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from ibme.core.encoding import encode_bytes
    from ibme.core.lamport_ots import LamportPublicKey, PUBLIC_BYTES, SIGNATURE_BYTES
    from ibme.protocol.baseline import Ciphertext, DOMAIN_SIGNATURE
    from ibme.protocol.byteauth import ByteAuthCiphertext, encode_bound_message
    from ibme.protocol.hybrid_hibe import HybridCiphertext

    rows = []
    for label, signature_bytes, message_bytes in (("A", 6237, 32), ("C", 3227824, 0)):
        observations = master["rows"][label]["installed_cli"]["observations"]
        original = next(row for row in observations if row["message_bytes"] == message_bytes)
        envelope = encode_bound_message(bytes(64), bytes(message_bytes))
        payload = DOMAIN_SIGNATURE + encode_bytes(bytes(signature_bytes)) + encode_bytes(envelope)
        hybrid = HybridCiphertext(bytes(64), b"x", bytes(12), bytes(len(payload) + 16))
        probe = ByteAuthCiphertext(bytes(64), LamportPublicKey(bytes(PUBLIC_BYTES)),
                                  Ciphertext(hybrid).to_bytes(), bytes(SIGNATURE_BYTES))
        overhead = len(probe.to_bytes()) - 1 - signature_bytes - message_bytes - PUBLIC_BYTES - SIGNATURE_BYTES
        capsule = original["ciphertext_bytes"] - PUBLIC_BYTES - SIGNATURE_BYTES - signature_bytes - message_bytes - overhead
        capacity = master["rows"][label]["installed_cli"]["capacity"]
        if not (0 < capsule <= capacity["inner_hibe_ciphertext_max_bytes"]):
            raise ValueError("capsule subtraction exceeds the recorded format limit")
        rows.append({"representative": label, "message_bytes": message_bytes,
                     "ots_public_bytes": PUBLIC_BYTES, "ots_signature_bytes": SIGNATURE_BYTES,
                     "ibs_signature_bytes": signature_bytes, "capsule_bytes": capsule,
                     "framing_and_tag_bytes": overhead, "total_bytes": original["ciphertext_bytes"],
                     "capsule_method": "recorded total minus exact fixed-format components"})
    return {"schema": "IBME-REPORT-FORMAT-ACCOUNTING/1", "new_encryptions": 0,
            "method": "serializer length probe plus existing public totals; capsule length inferred", "rows": rows}


def tables(data: dict, accounting: dict) -> dict[str, str]:
    master = data["master"]["rows"]
    result = {}
    result["ab-timings.tex"] = "\n".join(
        f"{title} & {number(master['A']['benchmark']['timing_seconds'][key]['median'])} & "
        f"{number(master['B']['benchmark']['timing_seconds'][key]['median'])} & "
        f"{master['A']['benchmark']['timing_seconds'][key]['count']}/{master['B']['benchmark']['timing_seconds'][key]['count']} \\\\"
        for title, key in OPERATIONS
    ) + "\n"
    rows = []
    for label in ("A", "B"):
        b = master[label]["benchmark"]
        values = [statistics.median([b["object_bytes"][key]["minimum"], b["object_bytes"][key]["maximum"]]) / 1024
                  for key in ("public.bin", "master.bin", "sender.bin", "receiver.bin")]
        values += [statistics.median([b["ciphertext_bytes"]["minimum"], b["ciphertext_bytes"]["maximum"]]) / 1024,
                   b["sampled_process_tree_peak_rss_bytes"] / 1024**2]
        rows.append(label + " & " + " & ".join(number(value) for value in values) + r" \\")
    result["ab-sizes.tex"] = "\n".join(rows) + "\n"
    rows = []
    for profile in ("PARAM-I", "PARAM-II", "PARAM-III"):
        selected = {r["object"]: r for r in data["codec"] if r["profile"] == profile}
        for mode in ("json", "compact"):
            values = [int(selected[k][mode + "_bytes_median"]) / 1024 for k in ("public", "master", "key", "signature")]
            rows.append(profile.replace("PARAM-", "") + ("／JSON" if mode == "json" else "／紧凑")
                        + " & " + " & ".join(number(v) for v in values) + r" \\")
    result["codec-sizes.tex"] = "\n".join(rows) + "\n"
    rows = []
    for label in ("I", "II"):
        record = data["sageloli_" + label]
        t = record["timings"]
        rows.append("PARAM-" + label + " & " + " & ".join(number(v) for v in
                    (t["setup"], t["extract"], t["first_sign"], t["second_sign"], t["verify"],
                     record["peak_rss_bytes"] / 1024**3)) + r" \\")
    result["sageloli-times.tex"] = "\n".join(rows) + "\n"
    rows = []
    for row in accounting["rows"]:
        values = [row[k] for k in ("ots_public_bytes", "ots_signature_bytes", "ibs_signature_bytes", "capsule_bytes",
                                   "message_bytes", "framing_and_tag_bytes", "total_bytes")]
        rows.append(row["representative"] + " & " + " & ".join(f"{v:,}" for v in values) + r" \\")
    result["ciphertext-parts.tex"] = "\n".join(rows) + "\n"
    combinations = ordered_combinations(data)
    rows = []
    for row in combinations:
        values = [float(row[key]) for key in (
            "setup_seconds", "sender-key_seconds", "receiver-key_seconds",
            "cold-encrypt_seconds", "first-decrypt_seconds",
        )]
        rows.append(COMBINATION_LABELS[row["case"]] + " & "
                    + " & ".join(number(value) for value in values) + r" \\")
    result["ten-first-times.tex"] = "\n".join(rows) + "\n"
    rows = []
    for row in combinations:
        values = [float(row[key]) for key in (
            "public_bytes", "master_bytes", "sender_bytes", "receiver_bytes", "ciphertext_bytes",
        )]
        rows.append(COMBINATION_LABELS[row["case"]] + " & "
                    + " & ".join(binary_size(value) for value in values) + r" \\")
    result["ten-object-sizes.tex"] = "\n".join(rows) + "\n"
    representatives = {label: next(row for row in combinations if row["case"] == name)
                       for label, name in REPRESENTATIVE_CASES.items()}
    metrics = [
        ("首次加密", "cold-encrypt_seconds", duration),
        ("首次解密", "first-decrypt_seconds", duration),
        ("重复加密", "warm-encrypt_seconds", duration),
        ("重复解密", "warm-decrypt_seconds", duration),
        ("恢复后解密", "restored-decrypt_seconds", duration),
        ("完整密文", "ciphertext_bytes", binary_size),
    ]
    rows = []
    for title, key, formatter in metrics:
        rows.append(title + " & " + " & ".join(
            formatter(float(representatives[label][key])) for label in ("A", "B", "C")) + r" \\")
    result["ten-representatives.tex"] = "\n".join(rows) + "\n"
    return result


def manifest() -> dict:
    paths = list(SOURCES.values()) + ["src/ibme/core/encoding.py", "src/ibme/core/lamport_ots.py",
            "src/ibme/protocol/baseline.py", "src/ibme/protocol/byteauth.py", "src/ibme/protocol/hybrid_hibe.py"]
    return {"schema": "IBME-REPORT-MATERIAL-SOURCES/1", "new_cryptographic_runs": 0,
            "sources": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}}


def plot_all(data: dict, accounting: dict, font: str | None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager, ticker
    from matplotlib.lines import Line2D
    import numpy as np
    candidates = ([Path(font)] if font else []) + [Path("C:/Windows/Fonts/msyh.ttc"), Path("/mnt/c/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]
    selected = next((p for p in candidates if p.is_file()), None)
    if selected is None:
        raise RuntimeError("Supply --font with a CJK font path")
    font_manager.fontManager.addfont(str(selected))
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=str(selected)).get_name(),
        "font.size": 11, "axes.titlesize": 12, "axes.labelsize": 11,
        "axes.spines.top": False, "axes.spines.right": False, "axes.unicode_minus": False,
        "figure.facecolor": "white", "savefig.facecolor": "white", "legend.frameon": False})
    colors = ["#285A87", "#D88B32", "#389C8B", "#8794AA", "#B25E79"]
    output = HERE / "figures"
    output.mkdir(exist_ok=True)
    def save(fig, name):
        fig.savefig(output / name, dpi=220, bbox_inches="tight", pad_inches=.12)
        plt.close(fig)

    fig, axis = plt.subplots(figsize=(8.2, 3.45), layout="constrained")
    operations = (("warm-encrypt", "重复加密", 1), ("warm-decrypt", "重复解密", 0))
    for i, label in enumerate(("A", "B")):
        for operation, _, y in operations:
            values = data["master"]["rows"][label]["benchmark"]["timing_seconds"][operation]["observations"]
            median = statistics.median(values)
            minimum, maximum = min(values), max(values)
            position = y + (.13 if label == "A" else -.13)
            axis.errorbar(median, position,
                          xerr=np.array([[median-minimum], [maximum-median]]),
                          fmt="o", color=colors[i], ecolor=colors[i],
                          markersize=7, elinewidth=2.2, capsize=4,
                          label=("A：LATTE＋BNN/ML-DSA" if label == "A" else "B：LATTE＋SRGG")
                          if operation == "warm-encrypt" else None)
            axis.annotate(f"{median:.3g} s", (median, position), xytext=(7, 5),
                          textcoords="offset points", color=colors[i], fontsize=10)
    axis.set_xscale("log")
    axis.set_xlim(.045, 75)
    axis.set_yticks([0, 1], ["重复解密", "重复加密"])
    axis.set_xlabel("完整协议耗时 / 秒（对数刻度）")
    axis.set_title("固定密钥下9次重复操作的中位数与极差")
    axis.grid(axis="x", which="both", alpha=.2)
    axis.legend(loc="center", bbox_to_anchor=(.57, .52))
    save(fig, "ab-times.png")

    combinations = ordered_combinations(data)
    representative_by_case = {case: label for label, case in REPRESENTATIVE_CASES.items()}
    plot_labels = [
        (representative_by_case.get(row["case"], "") + "  " if row["case"] in representative_by_case else "")
        + COMBINATION_LABELS[row["case"]]
        for row in combinations
    ]
    positions = np.arange(len(combinations))
    fig, axes = plt.subplots(1, 2, figsize=(9.1, 5.25), sharey=True, layout="constrained")
    time_panels = (
        (axes[0], (("cold-encrypt_seconds", "首次", "o", colors[0]),
                   ("warm-encrypt_seconds", "重复", "s", colors[1])), "完整加密"),
        (axes[1], (("first-decrypt_seconds", "首次", "o", colors[0]),
                   ("warm-decrypt_seconds", "重复", "s", colors[1]),
                   ("restored-decrypt_seconds", "恢复后", "^", colors[2])), "匹配解密"),
    )
    for axis, series, title in time_panels:
        for key, label, marker, color in series:
            values = [float(row[key]) for row in combinations]
            axis.scatter(values, positions, s=42, marker=marker, color=color,
                         edgecolor="white", linewidth=.45, zorder=3, label=label)
        axis.axhline(4.5, color="#9AA4B2", linewidth=.8)
        axis.set_xscale("log")
        axis.set_xlabel("时间 / 秒（对数刻度）")
        axis.set_title(title)
        axis.grid(axis="x", which="both", alpha=.2)
        axis.legend(loc="lower right", fontsize=9)
    axes[0].set_yticks(positions, plot_labels)
    axes[0].invert_yaxis()
    save(fig, "ten-combination-times.png")

    rss_fields = [key for key in combinations[0] if key.endswith("_sampled_rss_bytes")]
    ciphertext_mib = [float(row["ciphertext_bytes"]) / 1024**2 for row in combinations]
    peak_rss_gib = [max(float(row[key]) for key in rss_fields) / 1024**3 for row in combinations]
    fig, axes = plt.subplots(1, 2, figsize=(9.1, 5.25), layout="constrained")
    hibe_colors = [colors[0]] * 5 + [colors[1]] * 5
    axes[0].scatter(ciphertext_mib, positions, s=45, color=hibe_colors,
                    edgecolor="white", linewidth=.45, zorder=3)
    axes[0].set_xscale("log")
    axes[0].set_xlim(.1, 6)
    axes[0].xaxis.set_major_locator(ticker.FixedLocator([.125, .25, .5, 1, 2, 4]))
    axes[0].xaxis.set_major_formatter(ticker.FuncFormatter(lambda value, _: f"{value:g}"))
    axes[0].xaxis.set_minor_formatter(ticker.NullFormatter())
    axes[0].set_xlabel("完整密文 / MiB（对数刻度）")
    axes[0].set_title("完整密文长度")
    axes[1].scatter(peak_rss_gib, positions, s=45, color=hibe_colors,
                    edgecolor="white", linewidth=.45, zorder=3)
    axes[1].set_xlabel("各阶段最大采样RSS / GiB")
    axes[1].set_title("运行内存")
    for axis in axes:
        axis.axhline(4.5, color="#9AA4B2", linewidth=.8)
        axis.grid(axis="x", which="both", alpha=.2)
        axis.set_yticks(positions)
        axis.set_ylim(len(combinations) - .5, -.5)
    axes[0].set_yticklabels(plot_labels)
    axes[1].set_yticklabels([])
    axes[1].legend(handles=[
        Line2D([], [], marker="o", linestyle="", color=colors[0], label="LATTE"),
        Line2D([], [], marker="o", linestyle="", color=colors[1], label="Lai"),
    ], loc="lower right", fontsize=9)
    save(fig, "ten-combination-resources.png")
    (output / "representative-profile.png").unlink(missing_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(8, 5.6), layout="constrained")
    for axis, key, title in zip(axes.flat, ("public", "master", "key", "signature"),
                                ("公钥", "主状态", "用户密钥", "签名")):
        rows = [r for r in data["codec"] if r["object"] == key]
        positions = np.arange(3)
        for j, mode in enumerate(("json", "compact")):
            values = [int(r[mode + "_bytes_median"]) / 1024 for r in rows]
            axis.bar(positions+(j-.5)*.35, values, width=.35, color=colors[j], label=("JSON" if j==0 else "紧凑格式"))
        axis.set_xticks(positions, ["I", "II", "III"])
        axis.set_ylabel("编码长度 / KiB")
        axis.set_title(title)
        axis.grid(axis="y", alpha=.18)
    axes[0,0].legend(loc="upper left")
    save(fig, "codec.png")

    c = data["optimization"]["summary"]["C"]
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.8), layout="constrained")
    vals = [c["original_decrypt_seconds"], c["preparation_seconds"], c["prepared_decrypt_seconds"]]
    axes[0].bar(["原解密", "会话准备", "后续解密"], vals, color=colors[:3])
    for i,v in enumerate(vals): axes[0].text(i,v+12,f"{v:.1f}",ha="center",fontsize=11)
    axes[0].set_ylim(0,620); axes[0].set_ylabel("时间 / 秒")
    axes[0].set_title("实测阶段耗时")
    ns = np.arange(1,21)
    axes[1].plot(ns, [c["original_decrypt_seconds"]]*len(ns), color=colors[0], label="每条重新委派")
    axes[1].plot(ns, c["preparation_seconds"]/ns+c["prepared_decrypt_seconds"], "--", color=colors[2], label="会话摊销模型")
    axes[1].set_xlabel("同一身份对的消息条数")
    axes[1].set_ylabel("每条平均时间 / 秒")
    axes[1].set_title("计入准备的成本估算")
    axes[1].legend(fontsize=10)
    for axis in axes: axis.grid(axis="y",alpha=.18)
    save(fig,"session.png")

    fig, axis = plt.subplots(figsize=(8, 3.1), layout="constrained")
    fields = [("ots_public_bytes","一次性公钥"),("ots_signature_bytes","一次性签名"),
              ("capsule_bytes","HIBE胶囊"),("ibs_signature_bytes","IBS签名"),
              ("other","消息与格式")]
    left = np.zeros(2)
    for j,(key,title) in enumerate(fields):
        counts = [r[key] if key!="other" else r["message_bytes"]+r["framing_and_tag_bytes"] for r in accounting["rows"]]
        shares = np.array([100*value/r["total_bytes"] for value,r in zip(counts,accounting["rows"])])
        axis.barh([1,0], shares, left=left, color=colors[j], height=.5,label=title)
        for i,(start,share) in enumerate(zip(left,shares)):
            if share >= 4: axis.text(start+share/2,1-i,f"{share:.1f}%",ha="center",va="center",color="white",fontsize=10)
        left += shares
    axis.set_yticks([1,0], ["A：32 B消息\n合计138.8 KiB", "C：空消息\n合计4.34 MiB"])
    axis.set_xlabel("完整密文中的占比 / %")
    axis.set_xlim(0,100)
    axis.legend(ncol=3,loc="upper center",bbox_to_anchor=(.45,1.35),fontsize=10)
    save(fig,"ciphertext-parts.png")

    placement = data["placement"]["timing_seconds"]
    fig, axes = plt.subplots(1,2,figsize=(8,3.4),layout="constrained")
    names = ["Windows盘\n源码", "Windows盘\n安装包", "Linux盘\n同一安装包"]
    for axis,op,title in zip(axes,("encrypt","decrypt"),("完整加密","完整解密")):
        vals = [placement[key][op]["median"]*1000 for key in ("source","windows_wheel","wsl_wheel")]
        axis.bar(names, vals, color=colors[:3])
        for i,v in enumerate(vals): axis.text(i,v+4,f"{v:.1f}",ha="center",fontsize=10)
        axis.set_ylim(0,max(vals)*1.22)
        axis.set_ylabel("时间 / 毫秒");axis.set_title(title);axis.grid(axis="y",alpha=.18)
    save(fig,"placement.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", help="path to a CJK font")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    data = load_materials()
    accounting = frame_accounting(data["master"])
    folder = HERE / "tables"
    folder.mkdir(exist_ok=True)
    generated = tables(data, accounting)
    for name, content in generated.items():
        (folder/name).write_text(content,encoding="utf-8",newline="\n")
    for chapter in (HERE / "chapters").glob("*.tex"):
        original = chapter.read_text(encoding="utf-8")
        updated = original
        for name, content in generated.items():
            block = "% BEGIN DATA " + name + "\n" + content + "% END DATA " + name
            updated = updated.replace(r"\input{tables/" + name + "}", block)
            pattern = r"% BEGIN DATA " + re.escape(name) + r"\n.*?% END DATA " + re.escape(name)
            updated = re.sub(pattern, lambda _: block, updated, flags=re.DOTALL)
        if updated != original:
            chapter.write_text(updated, encoding="utf-8", newline="\n")
    for name, value in (("format-accounting.json",accounting),("material-sources.json",manifest())):
        (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not args.no_plots: plot_all(data, accounting, args.font)
    print("Prepared 8 data tables, format accounting and" + (" 7 figures" if not args.no_plots else " source bindings"))


if __name__ == "__main__":
    main()
