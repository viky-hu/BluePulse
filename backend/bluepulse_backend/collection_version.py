"""Identify the code and source entrances loaded by a running collector."""
from functools import cache
from hashlib import sha256
import json
import os
from pathlib import Path

from sqlalchemy.engine import make_url


IDENTITY_FIELDS = ("collection_rule_version", "collection_entry_fingerprint")
WORKER_IDENTITY_FIELDS = (*IDENTITY_FIELDS, "database_fingerprint")

_RULE_MODULES = (
    "ccgp_source", "collection_flow", "collection_recovery", "collection_version",
    "editorial", "editorial_copy", "europol_source", "htx_source",
    "live_sources", "material_identity", "nanjing_source", "pipeline", "police_science_source", "source_collection", "source_expansion",
    "source_listing", "source_page", "spf_source", "statescoop_source", "suzhou_source", "top5_probe", "worker",
)


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@cache
def _loaded_collection_identity():
    from .source_collection import SOURCE_REGISTRY, source_listing_entries

    directory = Path(__file__).resolve().parent
    rules = {name: (directory / f"{name}.py").read_text(encoding="utf-8") for name in _RULE_MODULES}
    entrances = {slug: {"kind": spec.kind, "host": spec.host, "entries": source_listing_entries(spec)}
                 for slug, spec in SOURCE_REGISTRY.items()}
    return _digest(rules), _digest(entrances)


def collection_identity():
    return dict(zip(IDENTITY_FIELDS, _loaded_collection_identity(), strict=True))


def sqlite_database_path(address):
    parsed = make_url(address)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, ":memory:"):
        return Path(parsed.database).resolve()
    return None


def worker_configuration(*, collection, model_budget, database):
    path = sqlite_database_path(database)
    return {"collection": collection, "model_budget": model_budget, **collection_identity(),
            "translation_enabled": os.environ.get("BLUEPULSE_TRANSLATION_ENABLED", "1") != "0",
            "database_fingerprint": _digest(os.path.normcase(str(path))) if path else None}
