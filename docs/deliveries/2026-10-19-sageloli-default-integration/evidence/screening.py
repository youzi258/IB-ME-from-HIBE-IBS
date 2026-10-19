"""Static execution-domain screening for Sageloli paper parameters.

No keys, no entropy, no sampling: this script only constructs parameter
records, records which local gates reject the paper points, and computes the
expanded negacyclic matrix sizes the current backend representation would
allocate.  It is screening evidence for planning, not a security claim and
not a feasibility verdict on the paper's algorithms.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from experiments.research.candidates.sageloli.config import RSISParams, SISParams  # noqa: E402

PAPER_POINTS = (
    {"label": "HAL v1 Table 4 point 1", "k": 65, "d": 2048, "l": 132},
    {"label": "HAL v1 Table 4 point 2", "k": 153, "d": 2048, "l": 308},
)

# Python-int + tuple-pointer lower bound per expanded matrix entry (CPython
# small-int cache does not apply to sampled coefficients).
BYTES_PER_ENTRY_MEMORY = 28 + 8
INT64_WIRE_BYTES_PER_ENTRY = 8
CODEC_MAX_WIRE_BYTES = 16 * 2**20
CODEC_MAX_DIMENSION_SQUARED = 4096**2


def rsis_violated_gates(k, d, l):
    """List every RSISParams gate the point violates, mirroring __post_init__."""

    gates = []
    if not 4 <= d <= 16:
        gates.append(f"d cap 4..16 violated (d={d})")
    if d & (d - 1):
        gates.append("d must be a power of two")
    if not 1 <= k <= 16:
        gates.append(f"k cap 1..16 violated (k={k})")
    if not k + 1 <= l <= 128:
        gates.append(f"l range k+1..128 violated (l={l}, needs {k + 1}..128)")
    if d * (l + k) > 128:
        gates.append(f"coefficient dimension cap 128 violated (d*(l+k)={d * (l + k)})")
    return gates


def expanded_sizes(k, d, l):
    """Entry counts of the expanded forms the RSIS backend materializes."""

    shapes = {
        "public_matrix": (d, d * l),
        "root_trapdoor": (d * (l - k), d * k),
        "identity_trapdoor": (d * l, d * k),
        "signature": (d * (l + k),),
    }
    out = {}
    for name, shape in shapes.items():
        entries = 1
        for dim in shape:
            entries *= dim
        wire = entries * INT64_WIRE_BYTES_PER_ENTRY
        out[name] = {
            "shape": list(shape),
            "entries": entries,
            "int64_wire_bytes": wire,
            "int64_wire_bytes_over_16MiB_budget": wire > CODEC_MAX_WIRE_BYTES,
            "wire_count_over_codec_dimension_cap": entries > CODEC_MAX_DIMENSION_SQUARED,
            "memory_lower_bound_bytes": entries * BYTES_PER_ENTRY_MEMORY,
        }
    return out


def rsis_executable_ceiling():
    """Largest coefficient dimensions admitted by the current gates."""

    best = []
    for d in (4, 8, 16):
        for k in range(1, 17):
            l = 128 // d - k
            if k + 1 <= l <= 128 and d * (l + k) <= 128:
                best.append({"d": d, "k": k, "l": l,
                             "coefficient_dimension": d * (l + k), "q_bits": k * 1.585})
    widest = max(best, key=lambda row: (row["k"], row["coefficient_dimension"]))
    deepest = max(best, key=lambda row: (row["d"], row["coefficient_dimension"]))
    return {"full_128_dimension_profiles": best,
            "largest_k": widest, "largest_d": deepest}


def sis_executable_ceiling():
    """Largest matrix profiles admitted by m >= 2nk and m+nk <= 128."""

    best = []
    for n in range(1, 9):
        for k in range(1, 17):
            nk = n * k
            m_low, m_high = 2 * nk, 128 - nk
            if nk <= 42 and m_low <= m_high:
                best.append({"n": n, "k": k, "m": m_high,
                             "coefficient_dimension": m_high + nk})
    return {
        "note": "paper publishes no concrete SIS point; ceilings are gate maxima only",
        "max_k": max(best, key=lambda row: (row["k"], row["coefficient_dimension"])),
        "max_n": max(best, key=lambda row: (row["n"], row["coefficient_dimension"])),
    }


def main():
    report = {
        "security_claim": "none",
        "backend_admitted": False,
        "parameters_are_formal": False,
        "paper_points": [],
        "rsis_executable_ceiling": rsis_executable_ceiling(),
        "sis_executable_ceiling": sis_executable_ceiling(),
        "conclusion": (
            "The paper RSIS points are rejected by the local parameter gates "
            "(d/k caps and the 128-coefficient-dimension cap) and, independent "
            "of those gates, the current expanded negacyclic representation "
            "would allocate multi-gigabyte to terabyte public-key/trapdoor "
            "objects far beyond the 16 MiB wire budget.  Running them requires "
            "an unexpanded ring-native execution domain plus gate changes, not "
            "a configuration edit."
        ),
    }
    for point in PAPER_POINTS:
        row = dict(point)
        row["violated_gates"] = rsis_violated_gates(point["k"], point["d"], point["l"])
        row["expanded_forms"] = expanded_sizes(point["k"], point["d"], point["l"])
        report["paper_points"].append(row)

    # The default research profiles still construct and roundtrip.
    for cls in (RSISParams, SISParams):
        record = cls().record()
        assert cls.from_record(record).record() == record

    out = Path(__file__).with_name("execution-domain-screening.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
    for row in report["paper_points"]:
        total = row["expanded_forms"]
        print(f"{row['label']}: {len(row['violated_gates'])} gate violations; "
              f"identity trapdoor >= {total['identity_trapdoor']['memory_lower_bound_bytes'] / 2**30:.1f} GiB "
              f"(expanded {total['identity_trapdoor']['shape']})")


if __name__ == "__main__":
    main()
