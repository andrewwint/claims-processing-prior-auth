"""The trusted, read-only synthetic stores, bundled with the code.

In a Lambda they are read from prior_auth/trusted/ (staged by
scripts/stage_bundle.py). In a checkout they are read from data/.
"""

import json
from functools import lru_cache
from pathlib import Path

_BUNDLED = Path(__file__).resolve().parent / "trusted"
_CHECKOUT = Path(__file__).resolve().parents[2] / "data"


def _root(name: str) -> Path:
    bundled = _BUNDLED / name
    if bundled.exists():
        return bundled
    return {"policies": _CHECKOUT / "policies" / "compiled", "charts": _CHECKOUT / "charts",
            "cases": _CHECKOUT / "cases"}[name]


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


@lru_cache(maxsize=None)
def criteria(payer_id: str, cpt_code: str) -> list[dict]:
    """Exact match on (payer, CPT); no retrieval. Empty means no verified policy."""
    path = _root("policies") / payer_id / f"{cpt_code}.json"
    return _load(path)["criteria"] if path.is_file() else []


@lru_cache(maxsize=None)
def chart_index() -> dict:
    return _load(_root("charts") / "index.json")["index"]


@lru_cache(maxsize=None)
def document(doc_id: str) -> dict | None:
    path = _root("charts") / f"{doc_id}.json"
    if not path.is_file() or path.name == "index.json":
        return None
    d = _load(path)
    return {"kind": d["kind"], "pages": d["pages"]}


def documents(doc_ids) -> dict:
    return {i: d for i in doc_ids if (d := document(i)) is not None}


@lru_cache(maxsize=None)
def cases() -> dict:
    return _load(_root("cases") / "cases.json")["cases"]


@lru_cache(maxsize=None)
def eligibility() -> dict:
    return _load(_root("cases") / "eligibility.json")["members"]


def request(case_id: str) -> dict | None:
    """The trusted request record for a case: never taken from the packet or the model."""
    c = cases().get(case_id)
    if c is None:
        return None
    return {k: c[k] for k in ("case_id", "patient_id", "member_id", "payer_id", "cpt_code", "tenant")}
