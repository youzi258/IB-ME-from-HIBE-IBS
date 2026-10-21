"""Read one user key and audit deterministic preparation; never sign or sample.

This checks numerical GS and fixed coordinate-width resource gates only.
It does not evaluate dynamic GPV centers, certify a distribution, or establish
that a signature can be produced. The input is never written or re-encoded.
"""
from __future__ import annotations

import argparse
import gc
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

from ibme.ibs.wang_pw_target.hashing import identity_matrix, inner_identity
from ibme.ibs.wang_pw_target.math import full_basis, gram_schmidt
from ibme.ibs.wang_pw_target.objects import MAX_WIRE_BYTES, SigningKey

from .run_lifecycle import RSSMonitor, safe_independent_failure_type
from .sign_independent import private_read


SCHEMA = "IBME/WANG-PW-RECOVERED-KEY-RESOURCE-AUDIT/1"
# Mirror native/gaussian.cpp's MAX_RADIUS; no native loading is needed.
MAX_RADIUS = 1 << 40
_REASONS = {
    "read-key": "private-input-rejected",
    "decode-key": "canonical-key-rejected",
    "user-basis": "basis-preparation-rejected",
    "public-matrix": "public-matrix-rejected",
    "user-qr": "numerical-preparation-rejected",
    "user-gs-gate": "numerical-gs-gate-rejected",
    "coordinate-widths": "coordinate-width-resource-rejected",
}


class PublicParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "invalid recovered-key-audit arguments\n")


class _Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error("duplicate option")
        setattr(namespace, self.dest, Path(values))


def _check(report, name, condition, *, resource=False):
    passed = bool(condition)
    report["observations"][name] = passed
    if not passed:
        if resource:
            report["status"] = "resource-rejected"
        raise ValueError("deterministic audit check rejected")


def main(argv=None):
    parser = PublicParser(prog="wang-pw-recovered-key-resource-audit",
                          description=__doc__, allow_abbrev=False)
    parser.add_argument("--key-file", required=True, action=_Once)
    args = parser.parse_args(argv)
    started = time.monotonic()
    monitor = RSSMonitor(.1)
    monitor.start()
    report = dict(schema=SCHEMA, status="failed", operation_stage="read-key",
                  issuer_inputs_provided=False, key_restored_without_issuer=False,
                  sampling_performed=False, dynamic_centers_checked=False,
                  distribution_certified=False, observations={}, security_claim="none",
                  backend_admitted=False, parameters_are_formal=False,
                  nist_security_category=None)
    try:
        raw = private_read(args.key_file, MAX_WIRE_BYTES)
        report["operation_stage"] = "decode-key"
        key = SigningKey.from_bytes(raw)
        report["key_restored_without_issuer"] = True
        del raw
        gc.collect()
        p, public_key = key.params, key.public_key
        report["operation_stage"] = "user-basis"
        public, basis = full_basis(public_key.a, key.trapdoor, p.q)
        _check(report, "basis_dimensions_match", basis.shape == (p.dimension, p.dimension))
        report["operation_stage"] = "public-matrix"
        _check(report, "public_dimensions_match", public.shape == (p.n, p.dimension))
        expected = identity_matrix(public_key, inner_identity(p, key.identity, key.identity_salt))
        _check(report, "public_matrix_matches_key",
               np.array_equal(public[:, :p.m], public_key.a)
               and np.array_equal(public[:, p.m:], expected))
        del public, expected
        report["operation_stage"] = "user-qr"
        star, norms, width = gram_schmidt(basis)
        del basis
        _check(report, "numerical_dimensions_match",
               star.shape == (p.dimension, p.dimension) and norms.shape == (p.dimension,))
        _check(report, "star_finite", np.all(np.isfinite(star)))
        _check(report, "norms_positive_finite",
               norms.size > 0 and np.all(np.isfinite(norms)) and np.all(norms > 0))
        del star
        report["operation_stage"] = "user-gs-gate"
        _check(report, "upper_gs_within_limit",
               math.isfinite(width) and 0 < width <= p.user_gs_limit, resource=True)
        report["operation_stage"] = "coordinate-widths"
        # Match Proposal's native resource test, without calling the sampler.
        with np.errstate(all="ignore"):
            coordinate_sigmas = p.sign_sigma / np.sqrt(norms)
        _check(report, "coordinate_widths_positive_finite",
               np.all(np.isfinite(coordinate_sigmas)) and np.all(coordinate_sigmas > 0),
               resource=True)
        _check(report, "coordinate_widths_within_resource_limit",
               np.all(coordinate_sigmas <= float(MAX_RADIUS) / p.gaussian_tail_sigma),
               resource=True)
        report.update(status="passed", operation_stage="complete")
    except BaseException as exc:
        report.update(failure_type=safe_independent_failure_type(type(exc).__name__),
                      failure_reason=_REASONS[report["operation_stage"]])
    finally:
        report.update(duration_seconds=time.monotonic() - started, **monitor.finish())
    print(json.dumps(report, sort_keys=True, allow_nan=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
