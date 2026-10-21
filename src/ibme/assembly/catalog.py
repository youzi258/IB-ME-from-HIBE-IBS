"""The nineteen literature routes, distinct from executable backend variants.

This module never imports an algorithm or reads randomness.  It reports the
coordinator-owned security of completed profiles already attached to registry descriptors;
it does not infer admission from availability or test execution.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AlgorithmRoute:
    id: str
    role: str
    backends: tuple[str, ...]


ROUTES = (
    AlgorithmRoute("abb-rom", "hibe", ("abb-rom", "abb10")),
    AlgorithmRoute("chkp-rom", "hibe", ("chkp", "mp12-chkp-reference", "mp12-structured-hg")),
    AlgorithmRoute("latte", "hibe", ("latte",)),
    AlgorithmRoute("gkr2025", "hibe", ("gkr2025",)),
    AlgorithmRoute("zhang2020", "hibe", ("zhang2020",)),
    AlgorithmRoute("abb-standard-selective", "hibe", ("abb-standard-selective",)),
    AlgorithmRoute("chkp-standard", "hibe", ("chkp-standard",)),
    AlgorithmRoute("lai-ideal-hibe", "hibe", ("lai-ideal-hibe",)),
    AlgorithmRoute("luo-matrix", "ibs", ("luo-matrix",)),
    AlgorithmRoute("luo-module", "ibs", ("luo-module",)),
    AlgorithmRoute("srgg2025", "ibs", ("srgg2025", "srgg2025-paper")),
    AlgorithmRoute("yu2026", "ibs", ("yu2026",)),
    AlgorithmRoute("sageloli-sis", "ibs", ("sageloli-sis",)),
    AlgorithmRoute("sageloli-rsis", "ibs", ("sageloli-rsis",)),
    AlgorithmRoute("foo-li", "ibs", ("foo-li",)),
    AlgorithmRoute("wang-pw", "ibs", ("wang-pw", "wang-pw-target")),
    AlgorithmRoute("cert-ml-dsa", "ibs", ("cert-ml-dsa",)),
    AlgorithmRoute("cert-falcon", "ibs", ("cert-falcon",)),
    AlgorithmRoute("xie-ntru-ibs", "ibs", ("xie-ntru-ibs",)),
)


def algorithm_catalog(*, registry=None):
    """Report every route even when it has no runnable common adapter.

    An available registry descriptor means an interface can be constructed,
    not that this route has passed any particular combination test.
    """
    from .registry import default_backend_catalog
    listing = registry.list() if registry is not None else default_backend_catalog()
    registered = {(s["id"], role): s for role, specs in listing.items()
                  for s in specs}
    rows = []
    for route in ROUTES:
        entries = [registered[name, route.role] for name in route.backends
                   if (name, route.role) in registered]
        admitted = [entry for entry in entries if entry["backend_admitted"]]
        rows.append(dict(
            id=route.id, role=route.role, backend_ids=list(route.backends),
            registered_backends=entries,
            adapter_available=any(s["available"] for s in entries),
            runtime_available=any(s["available"] and s["runtime_available"] for s in entries),
            combination_status="awaiting_selected_combination_acceptance",
            execution="not_executed",
            security_claim="secure" if admitted else "none",
            backend_admitted=bool(admitted),
            admitted_backends=[entry["id"] for entry in admitted],
            formal_parameter_presets={entry["id"]:entry["formal_parameter_presets"]
                                      for entry in admitted},
        ))
    return dict(kind="algorithm_route_catalog", counts={
        role: sum(row["role"] == role for row in rows) for role in ("hibe", "ibs")
    }, admitted_counts={
        role: sum(row["role"] == role and row["backend_admitted"] for row in rows)
        for role in ("hibe", "ibs")
    }, routes=rows, execution="not_executed", security_claim="per-route")
