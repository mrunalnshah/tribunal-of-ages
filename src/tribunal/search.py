"""Hybrid search over laws. Qdrant, embeddings and reranking all hide behind LawIndex.

Callers ask `index.search("he ate my pizza", ["ancient"])` and get laws by relevance. How the
vectors are built, stored, fused and re-scored is this module's secret, so it can change
(new models, new database settings) without touching any caller.
"""

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models

from tribunal.models import Law

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
SPARSE_MODEL = "Qdrant/bm25"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
ID_NAMESPACE = uuid.UUID("5b2f6a52-4c1e-4f8a-9d3b-7a1c0e9f2d44")


class SearchUnavailable(Exception):
    """Qdrant could not be reached, or it rejected the query."""


@dataclass
class Hit:
    law: Law
    score: float  # higher is more relevant


def container_cpus(cgroup: Path = Path("/sys/fs/cgroup")) -> int | None:
    """The CPUs this container may use, from its cgroup quota, or None without a quota.

    The models size their thread pools to every core on the machine. Inside a 2-CPU quota,
    those threads are paused in turns, and every request slows down, even the trivial ones.
    """
    try:
        quota, period = (cgroup / "cpu.max").read_text().split()  # cgroup v2: "200000 100000"
    except (OSError, ValueError):
        try:  # cgroup v1, on older hosts
            quota = (cgroup / "cpu" / "cpu.cfs_quota_us").read_text().strip()
            period = (cgroup / "cpu" / "cpu.cfs_period_us").read_text().strip()
        except OSError:
            return None
    try:
        return max(1, int(quota) // int(period)) if int(quota) > 0 else None
    except ValueError:  # "max": no quota at all
        return None


class Models:
    """The three local ONNX models. Loading takes seconds and real memory, so do it once."""

    def __init__(self, cache_dir: str, threads: int | None = None):
        threads = threads or container_cpus()  # None outside a container: every core
        self.dense = TextEmbedding(DENSE_MODEL, cache_dir=cache_dir, threads=threads)
        self.sparse = SparseTextEmbedding(SPARSE_MODEL, cache_dir=cache_dir, threads=threads)
        self.reranker = TextCrossEncoder(RERANK_MODEL, cache_dir=cache_dir, threads=threads)


class LawIndex:
    def __init__(self, client: QdrantClient, encoders: Models, alias: str = "laws"):
        self._client = client
        self._m = encoders
        self._alias = alias

    def rebuild(self, laws: list[Law]) -> str:
        """Index `laws` into a new collection, then point the alias at it.

        Queries keep using the old collection until the alias switch, which is atomic, so
        reindexing never causes downtime. Returns the new collection's name.
        """
        if not laws:
            raise ValueError("no laws to index: run `uv run tribunal curate` first")
        name = f"{self._alias}_{time.strftime('%Y%m%d%H%M%S')}"
        texts = [_embedding_text(law) for law in laws]
        dense = [vector.tolist() for vector in self._m.dense.passage_embed(texts)]
        sparse = list(self._m.sparse.embed(texts))
        self._client.create_collection(
            name,
            vectors_config={
                "dense": models.VectorParams(size=len(dense[0]), distance=models.Distance.COSINE)
            },
            sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        points = [
            models.PointStruct(
                id=_point_id(law.law_id),
                vector={"dense": d, "bm25": _sparse(s)},
                payload=law.model_dump(),
            )
            for law, d, s in zip(laws, dense, sparse, strict=True)
        ]
        self._client.upload_points(name, points, batch_size=64)
        for field in ("theme", "jurisdiction"):
            self._client.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)
        self._client.create_payload_index(name, "sensitive", models.PayloadSchemaType.BOOL)
        self._switch_alias(name)
        return name

    def search(
        self,
        query: str,
        themes: list[str] | None = None,
        jurisdiction: str | None = None,
        limit: int = 8,
    ) -> list[Hit]:
        """The best laws for `query` from the given themes (or all), most relevant first.

        Sensitive laws never appear: that filter isn't optional.
        """
        only = _filter(themes, jurisdiction)
        dense = next(iter(self._m.dense.query_embed(query))).tolist()
        sparse = _sparse(next(iter(self._m.sparse.query_embed(query))))
        try:
            result = self._client.query_points(
                self._alias,
                prefetch=[
                    models.Prefetch(query=dense, using="dense", filter=only, limit=30),
                    models.Prefetch(query=sparse, using="bm25", filter=only, limit=30),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=30,  # fetch more candidates than we return: the reranker picks
            )
        except Exception as err:  # qdrant-client raises different types per transport
            raise SearchUnavailable(f"search failed: {err}") from err
        hits = [Hit(Law.model_validate(point.payload), point.score) for point in result.points]
        return self._rerank(query, hits)[:limit]

    def _rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        """Re-score candidates with a cross-encoder, which reads query and law together."""
        if not hits:
            return hits
        scores = self._m.reranker.rerank(query, [_embedding_text(hit.law) for hit in hits])
        rescored = [Hit(hit.law, float(s)) for hit, s in zip(hits, scores, strict=True)]
        return sorted(rescored, key=lambda hit: hit.score, reverse=True)

    def get(self, law_id: str) -> Law | None:
        points = self._client.retrieve(self._alias, ids=[_point_id(law_id)], with_payload=True)
        return Law.model_validate(points[0].payload) if points else None

    def count(self) -> int:
        return self._client.count(self._alias).count

    def _switch_alias(self, name: str) -> None:
        create = models.CreateAlias(collection_name=name, alias_name=self._alias)
        operations: list[models.AliasOperations] = [
            models.CreateAliasOperation(create_alias=create),
        ]
        if any(a.alias_name == self._alias for a in self._client.get_aliases().aliases):
            delete = models.DeleteAlias(alias_name=self._alias)
            operations.insert(0, models.DeleteAliasOperation(delete_alias=delete))
        self._client.update_collection_aliases(change_aliases_operations=operations)
        for collection in self._client.get_collections().collections:
            if collection.name.startswith(f"{self._alias}_") and collection.name != name:
                self._client.delete_collection(collection.name)  # keep storage small


def _filter(themes: list[str] | None, jurisdiction: str | None) -> models.Filter:
    conditions: list[models.Condition] = [
        models.FieldCondition(key="sensitive", match=models.MatchValue(value=False)),
    ]
    if themes:
        conditions.append(models.FieldCondition(key="theme", match=models.MatchAny(any=themes)))
    if jurisdiction:
        match = models.MatchValue(value=jurisdiction)
        conditions.append(models.FieldCondition(key="jurisdiction", match=match))
    return models.Filter(must=conditions)


def _embedding_text(law: Law) -> str:
    """What gets embedded: the modern summary bridges today's words to the archaic text."""
    return f"{law.summary} {law.punishment}. {law.text}"


def _sparse(embedding) -> models.SparseVector:
    return models.SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())


def _point_id(law_id: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, law_id))
