"""OpenAI-compatible model steps using the same durable gateway."""
from dataclasses import dataclass
import json
import math
import os
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from .editorial import input_hash
from .editorial_models import EmbeddingVector
from .live_model import LiveAnalyzer, ProviderRejected, load_local_credentials
from .receipts import PaidGateway
from .work_queue import serialized


def _identity(endpoint, payload):
    messages = payload.get("messages", [])
    return {"endpoint": endpoint, "parameters": {k: v for k, v in payload.items() if k != "messages"},
            "prompt_hash": input_hash(messages[0]["content"]), "input_hash": input_hash(messages[1]["content"])}


@dataclass
class Steps:
    engine: object
    client: object
    presets: dict
    settings: dict
    subject: str
    budget: object
    run_key: str | None = None
    clock: object = None
    generation: str | None = None
    pins: dict | None = None

    def credentials(self, alias):
        base, key, model = load_local_credentials(self.presets[alias])
        if self.pins and self.pins.get(alias) != input_hash(json.dumps([base, model])):
            raise ValueError("model_configuration_changed")
        return base, key, model

    def __call__(self, capability, purpose, prompt, inputs, tokens):
        alias = self.settings.get(capability, "default")
        base, key, model = self.credentials(alias)
        analyzer = LiveAnalyzer(self.client, base, key, model)
        gateway = PaidGateway(self.engine, service=urlsplit(base).hostname, budget=self.budget,
                              run_key=self.run_key, redact=analyzer._redact,
                              **({"clock": self.clock} if self.clock else {}))
        endpoint = base.rstrip("/") + "/chat/completions"

        def request(payload, send):
            identity = {**_identity(endpoint, payload), "generation": self.generation}
            return gateway.request(self.subject, purpose, identity, send)

        result, meta, _ = analyzer._chat(prompt, json.dumps(inputs, ensure_ascii=False, sort_keys=True), tokens,
                                         request=request)
        if not isinstance(result, dict):
            raise ValueError("invalid_model_output")
        return result, meta

    def embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        base, key, model = self.credentials(self.settings["embedding"])
        endpoint = base.rstrip("/") + "/embeddings"
        analyzer = LiveAnalyzer(self.client, base, key, model)
        gateway = PaidGateway(self.engine, service=urlsplit(base).hostname, budget=self.budget,
                              run_key=self.run_key, redact=analyzer._redact,
                              **({"clock": self.clock} if self.clock else {}))
        config = input_hash(json.dumps([endpoint, model]))
        hashes = [input_hash(value) for value in texts]
        by_hash = dict(zip(hashes, texts))
        with Session(self.engine) as session:
            vectors = {row.text_hash: row.vector for row in session.scalars(select(EmbeddingVector).where(
                EmbeddingVector.config_hash == config, EmbeddingVector.text_hash.in_(list(by_hash))
            ))}
        missing = sorted(set(by_hash) - set(vectors))
        dimension = len(next(iter(vectors.values()))) if vectors else None
        for offset in range(0, len(missing), 10):
            batch_hashes = missing[offset:offset + 10]
            batch = [by_hash[digest] for digest in batch_hashes]

            def send():
                return self.client.post(endpoint, json={"model": model, "input": batch, "encoding_format": "float"},
                                        headers={"Authorization": "Bearer " + key}, follow_redirects=False)

            response = gateway.request("embeddings", f"embed:{input_hash(json.dumps(batch_hashes))[:24]}",
                                       {"endpoint": endpoint, "model": model, "texts": batch_hashes}, send)
            if response.status_code != 200:
                raise ProviderRejected(f"provider_http_{response.status_code}")
            rows = response.json().get("data")
            if not isinstance(rows, list) or len(rows) != len(batch):
                raise ValueError("invalid_embeddings")
            ordered = sorted(rows, key=lambda row: row["index"])
            if [row["index"] for row in ordered] != list(range(len(batch))):
                raise ValueError("invalid_embedding_indices")
            for digest, row in zip(batch_hashes, ordered):
                vector = row.get("embedding")
                if not isinstance(vector, list) or not vector or len(vector) > 8192 or any(
                    type(value) not in {float, int} or not math.isfinite(value) for value in vector
                ) or dimension is not None and len(vector) != dimension:
                    raise ValueError("invalid_embedding")
                dimension = len(vector)
                vectors[digest] = vector
            with serialized(self.engine) as session:
                for digest in batch_hashes:
                    if session.get(EmbeddingVector, (config, digest)) is None:
                        session.add(EmbeddingVector(config_hash=config, text_hash=digest, vector=vectors[digest]))
        return [vectors[digest] for digest in hashes]


def environment_models() -> dict:
    settings = json.loads(os.environ.get("BLUEPULSE_MODELS", "{}"))
    if not isinstance(settings, dict) or any(not isinstance(value, str) for value in settings.values()):
        raise ValueError("invalid_model_settings")
    return settings
