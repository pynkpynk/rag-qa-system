from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import Boolean, Integer, String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class HybridHit:
    chunk_id: str
    document_id: str
    filename: str | None
    page: int | None
    chunk_index: int
    text: str
    score: float
    rank_fts: int | None
    rank_vec: int | None
    vec_distance: float | None
    rank_trgm: int | None
    trgm_sim: float | None


@dataclass(frozen=True)
class HybridMeta:
    fts_count: int
    vec_count: int
    trgm_count: int
    vec_min_distance: float | None
    vec_max_distance: float | None
    vec_avg_distance: float | None
    trgm_min_sim: float | None
    trgm_max_sim: float | None
    trgm_avg_sim: float | None


def _to_pgvector_literal(emb: Sequence[float]) -> str:
    """
    pgvector のテキスト表現: "[0.1,0.2,...]"
    - ドライバ側のvectorアダプタ登録に依存しない（CASTでvector化する）
    """
    return "[" + ",".join(str(float(x)) for x in emb) + "]"


def hybrid_search_chunks_rrf(
    db: Session,
    *,
    owner_sub: str | None,
    owner_sub_alt: str | None = None,
    document_ids: Sequence[str] | None,
    query_text: str,
    query_embedding: Sequence[float],
    top_k: int = 20,
    fts_k: int = 50,
    vec_k: int = 50,
    rrf_k: int = 60,
    trgm_k: int = 0,
    trgm_limit: float = 0.0,
    trgm_like_patterns: Sequence[str] | None = None,
    use_fts: bool = True,
    use_trgm: bool = False,
    allow_all_without_owner: bool = False,
) -> tuple[list[HybridHit], HybridMeta]:
    """
    FTS/Vec/Trgm の上位を取り、RRFで統合して top_k を返す。
    - documents.owner_sub = :owner_sub (or alt) でテナント分離を担保
    - owner_sub/doc_ids が指定されない場合は allow_all_without_owner=True が必要（admin用途）
    """
    if owner_sub is None and not document_ids and not allow_all_without_owner:
        raise ValueError("owner_sub or document_ids required to scope search")
    if not isinstance(query_text, str) or not query_text.strip():
        raise ValueError("query_text must not be empty")
    if not query_embedding:
        raise ValueError("query_embedding must not be empty")

    if top_k <= 0:
        raise ValueError("top_k must be > 0")
    if vec_k <= 0:
        raise ValueError("vec_k must be > 0")
    if rrf_k <= 0:
        raise ValueError("rrf_k must be > 0")

    doc_ids = [str(doc_id) for doc_id in (document_ids or []) if str(doc_id)]
    use_doc_filter = bool(doc_ids)

    q_emb = _to_pgvector_literal(query_embedding)
    trgm_patterns = [pattern for pattern in (trgm_like_patterns or []) if pattern]
    use_trgm = bool(use_trgm and trgm_k > 0)
    use_fts = bool(use_fts and fts_k > 0)

    sql = text(
        """
WITH
params AS (
  SELECT
    websearch_to_tsquery('simple', :q) AS tsq,
    CAST(:q_emb AS vector) AS qvec,
    CAST(:rrf_k AS int) AS rrf_k,
    CAST(:use_doc_filter AS boolean) AS use_doc_filter,
    CAST(:use_fts AS boolean) AS use_fts,
    CAST(:use_trgm AS boolean) AS use_trgm,
    set_config('pg_trgm.similarity_threshold', :trgm_limit, true) AS _trgm_threshold_set
),
fts AS (
  SELECT
    c.id AS chunk_id,
    ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.fts, p.tsq) DESC) AS r_fts
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    p.use_fts = true
    AND (
      :owner_sub IS NULL
      OR d.owner_sub = :owner_sub
      OR (:owner_sub_alt IS NOT NULL AND d.owner_sub = :owner_sub_alt)
    )
    AND d.status = 'indexed'
    AND (
      p.use_doc_filter = false
      OR CAST(c.document_id AS text) = ANY(:doc_ids)
    )
    AND c.fts @@ p.tsq
  ORDER BY ts_rank_cd(c.fts, p.tsq) DESC
  LIMIT :fts_k
),
vec AS (
  SELECT
    c.id AS chunk_id,
    ROW_NUMBER() OVER (ORDER BY (c.embedding <=> p.qvec) ASC) AS r_vec,
    (c.embedding <=> p.qvec) AS dist
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    (
      :owner_sub IS NULL
      OR d.owner_sub = :owner_sub
      OR (:owner_sub_alt IS NOT NULL AND d.owner_sub = :owner_sub_alt)
    )
    AND d.status = 'indexed'
    AND (
      p.use_doc_filter = false
      OR CAST(c.document_id AS text) = ANY(:doc_ids)
    )
    AND c.embedding IS NOT NULL
  ORDER BY (c.embedding <=> p.qvec) ASC
  LIMIT :vec_k
),
trgm AS (
  SELECT
    c.id AS chunk_id,
    ROW_NUMBER() OVER (ORDER BY similarity(c.text, :q) DESC) AS r_trgm,
    similarity(c.text, :q) AS sim
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    p.use_trgm = true
    AND (
      :owner_sub IS NULL
      OR d.owner_sub = :owner_sub
      OR (:owner_sub_alt IS NOT NULL AND d.owner_sub = :owner_sub_alt)
    )
    AND d.status = 'indexed'
    AND (
      p.use_doc_filter = false
      OR CAST(c.document_id AS text) = ANY(:doc_ids)
    )
    AND (
      cardinality(:trgm_like_patterns) = 0
      OR c.text ILIKE ANY(:trgm_like_patterns)
    )
    AND c.text % :q
  ORDER BY similarity(c.text, :q) DESC
  LIMIT :trgm_k
),
rrf AS (
  SELECT
    src.chunk_id,
    SUM(1.0 / (p.rrf_k + src.rank)) AS score
  FROM (
    SELECT chunk_id, r_fts AS rank FROM fts
    UNION ALL
    SELECT chunk_id, r_vec AS rank FROM vec
    UNION ALL
    SELECT chunk_id, r_trgm AS rank FROM trgm
  ) src
  CROSS JOIN params p
  GROUP BY src.chunk_id
),
picked AS (
  SELECT
    c.id,
    c.document_id,
    d.filename,
    c.page,
    c.chunk_index,
    c.text,
    r.score,
    vec.dist AS vec_distance,
    fts.r_fts,
    vec.r_vec,
    trgm.r_trgm,
    trgm.sim AS trgm_sim
  FROM rrf r
  JOIN chunks c ON c.id = r.chunk_id
  JOIN documents d ON d.id = c.document_id
  LEFT JOIN vec ON vec.chunk_id = c.id
  LEFT JOIN fts ON fts.chunk_id = c.id
  LEFT JOIN trgm ON trgm.chunk_id = c.id
  ORDER BY r.score DESC, c.id ASC
  LIMIT :top_k
),
meta AS (
  SELECT
    (SELECT COUNT(*) FROM fts) AS fts_count,
    (SELECT COUNT(*) FROM vec) AS vec_count,
    (SELECT COUNT(*) FROM trgm) AS trgm_count,
    (SELECT MIN(dist) FROM vec) AS vec_min_distance,
    (SELECT MAX(dist) FROM vec) AS vec_max_distance,
    (SELECT AVG(dist) FROM vec) AS vec_avg_distance,
    (SELECT MIN(sim) FROM trgm) AS trgm_min_sim,
    (SELECT MAX(sim) FROM trgm) AS trgm_max_sim,
    (SELECT AVG(sim) FROM trgm) AS trgm_avg_sim
)
SELECT
  p.id,
  p.document_id,
  p.filename,
  p.page,
  p.chunk_index,
  p.text,
  p.score,
  p.vec_distance,
  p.r_fts,
  p.r_vec,
  p.r_trgm,
  p.trgm_sim,
  m.fts_count,
  m.vec_count,
  m.trgm_count,
  m.vec_min_distance,
  m.vec_max_distance,
  m.vec_avg_distance,
  m.trgm_min_sim,
  m.trgm_max_sim,
  m.trgm_avg_sim
FROM meta m
LEFT JOIN picked p ON true
ORDER BY p.score DESC NULLS LAST, p.id ASC NULLS LAST;
"""
    ).bindparams(
        bindparam("q", type_=String()),
        bindparam("owner_sub", type_=String()),
        bindparam("owner_sub_alt", type_=String()),
        bindparam("q_emb", type_=String()),
        bindparam("rrf_k", type_=Integer()),
        bindparam("use_doc_filter", type_=Boolean()),
        bindparam("use_fts", type_=Boolean()),
        bindparam("use_trgm", type_=Boolean()),
        bindparam("trgm_limit", type_=String()),
        bindparam("trgm_like_patterns", type_=ARRAY(String())),
        bindparam("doc_ids", type_=ARRAY(String())),
        bindparam("top_k", type_=Integer()),
        bindparam("fts_k", type_=Integer()),
        bindparam("vec_k", type_=Integer()),
        bindparam("trgm_k", type_=Integer()),
    )

    rows = (
        db.execute(
            sql,
            {
                "owner_sub": owner_sub,
                "owner_sub_alt": owner_sub_alt,
                "q": query_text,
                "q_emb": q_emb,
                "rrf_k": rrf_k,
                "use_doc_filter": use_doc_filter,
                "use_fts": use_fts,
                "use_trgm": use_trgm,
                "trgm_limit": f"{float(trgm_limit):.6f}",
                "trgm_like_patterns": trgm_patterns,
                "doc_ids": doc_ids or [],
                "top_k": top_k,
                "fts_k": fts_k,
                "vec_k": vec_k,
                "trgm_k": trgm_k if use_trgm else 0,
            },
        )
        .mappings()
        .all()
    )

    hits: list[HybridHit] = []
    for r in rows:
        if r.get("id") is None:
            continue
        hits.append(
            HybridHit(
                chunk_id=r["id"],
                document_id=r["document_id"],
                filename=r.get("filename"),
                page=r["page"],
                chunk_index=r["chunk_index"],
                text=r["text"],
                score=float(r["score"]),
                rank_fts=(int(r["r_fts"]) if r["r_fts"] is not None else None),
                rank_vec=(int(r["r_vec"]) if r["r_vec"] is not None else None),
                vec_distance=(
                    float(r["vec_distance"])
                    if r.get("vec_distance") is not None
                    else None
                ),
                rank_trgm=(
                    int(r["r_trgm"]) if r.get("r_trgm") is not None else None
                ),
                trgm_sim=(
                    float(r["trgm_sim"]) if r.get("trgm_sim") is not None else None
                ),
            )
        )

    meta_row = rows[0] if rows else {}
    meta = HybridMeta(
        fts_count=int(meta_row.get("fts_count") or 0),
        vec_count=int(meta_row.get("vec_count") or 0),
        trgm_count=int(meta_row.get("trgm_count") or 0),
        vec_min_distance=(
            float(meta_row["vec_min_distance"])
            if meta_row.get("vec_min_distance") is not None
            else None
        ),
        vec_max_distance=(
            float(meta_row["vec_max_distance"])
            if meta_row.get("vec_max_distance") is not None
            else None
        ),
        vec_avg_distance=(
            float(meta_row["vec_avg_distance"])
            if meta_row.get("vec_avg_distance") is not None
            else None
        ),
        trgm_min_sim=(
            float(meta_row["trgm_min_sim"])
            if meta_row.get("trgm_min_sim") is not None
            else None
        ),
        trgm_max_sim=(
            float(meta_row["trgm_max_sim"])
            if meta_row.get("trgm_max_sim") is not None
            else None
        ),
        trgm_avg_sim=(
            float(meta_row["trgm_avg_sim"])
            if meta_row.get("trgm_avg_sim") is not None
            else None
        ),
    )

    return hits, meta
