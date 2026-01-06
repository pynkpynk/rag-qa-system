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
    q_trgm: str | None = None,
    q_trgm_text: str | None = None,
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
    if vec_k < 0:
        raise ValueError("vec_k must be >= 0")
    if rrf_k <= 0:
        raise ValueError("rrf_k must be > 0")

    doc_ids = [str(doc_id) for doc_id in (document_ids or []) if str(doc_id)]
    use_doc_filter = bool(doc_ids)

    q_emb = _to_pgvector_literal(query_embedding)
    if q_trgm is None and q_trgm_text is not None:
        q_trgm = q_trgm_text
    q_trgm = query_text if q_trgm is None else q_trgm
    trgm_patterns = [pattern for pattern in (trgm_like_patterns or []) if pattern]
    use_trgm = bool(use_trgm and trgm_k > 0)
    use_fts = bool(use_fts and fts_k > 0)
    use_like_fallback = bool(
        trgm_patterns and (not use_trgm) and fts_k <= 0 and vec_k <= 0
    )

    if use_like_fallback:
        at_patterns = [p for p in trgm_patterns if "@" in p]
        base_patterns = [p for p in trgm_patterns if p not in at_patterns]
        at_pattern = at_patterns[0] if at_patterns else "%@%"
        extra_clause = (
            "\n  AND c.text ILIKE ANY(:trgm_like_patterns)" if base_patterns else ""
        )
        like_sql = text(
            f"""
SELECT
  c.id,
  c.document_id,
  d.filename,
  c.page,
  c.chunk_index,
  c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE
  d.status = 'indexed'
  AND (
    :owner_sub IS NULL
    OR d.owner_sub = :owner_sub
    OR (:owner_sub_alt IS NOT NULL AND d.owner_sub = :owner_sub_alt)
  )
  AND (
    :use_doc_filter = false
    OR CAST(c.document_id AS text) = ANY(:doc_ids)
  )
  AND c.text ILIKE :at_pattern{extra_clause}
ORDER BY c.page NULLS LAST, c.chunk_index ASC, c.id ASC
LIMIT :top_k
            """
        ).bindparams(
            bindparam("owner_sub", type_=String()),
            bindparam("owner_sub_alt", type_=String()),
            bindparam("use_doc_filter", type_=Boolean()),
            bindparam("doc_ids", type_=ARRAY(String())),
            bindparam("at_pattern", type_=String()),
            bindparam("top_k", type_=Integer()),
        )
        if base_patterns:
            like_sql = like_sql.bindparams(
                bindparam("trgm_like_patterns", type_=ARRAY(String())),
            )
        params = {
            "owner_sub": owner_sub,
            "owner_sub_alt": owner_sub_alt,
            "use_doc_filter": use_doc_filter,
            "doc_ids": doc_ids or [],
            "at_pattern": at_pattern,
            "top_k": top_k,
        }
        if base_patterns:
            params["trgm_like_patterns"] = base_patterns
        rows = db.execute(like_sql, params).mappings()
        hits: list[HybridHit] = []
        for rank, r in enumerate(rows, start=1):
            hits.append(
                HybridHit(
                    chunk_id=r["id"],
                    document_id=r["document_id"],
                    filename=r.get("filename"),
                    page=r["page"],
                    chunk_index=r["chunk_index"],
                    text=r["text"],
                    score=max(0.0, 1.0 - (rank - 1) * 0.001),
                    rank_fts=None,
                    rank_vec=None,
                    vec_distance=None,
                    rank_trgm=rank,
                    trgm_sim=None,
                )
            )
        meta = HybridMeta(
            fts_count=0,
            vec_count=0,
            trgm_count=len(hits),
            vec_min_distance=None,
            vec_max_distance=None,
            vec_avg_distance=None,
            trgm_min_sim=None,
            trgm_max_sim=None,
            trgm_avg_sim=None,
        )
        return hits, meta

    trgm_threshold_line = (
        "\n    , set_config('pg_trgm.similarity_threshold', :trgm_limit, true) AS _trgm_threshold_set"
        if use_trgm
        else ""
    )
    trgm_cte = (
        """
, trgm AS (
  SELECT
    c.id AS chunk_id,
    ROW_NUMBER() OVER (ORDER BY similarity(c.text, :q_trgm) DESC) AS r_trgm,
    similarity(c.text, :q_trgm) AS sim
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
    AND c.text % :q_trgm
  ORDER BY similarity(c.text, :q_trgm) DESC
  LIMIT :trgm_k
)
"""
        if use_trgm
        else ""
    )
    trgm_union = (
        """
    UNION ALL
    SELECT chunk_id, r_trgm AS rank FROM trgm
"""
        if use_trgm
        else ""
    )
    trgm_join = (
        "  LEFT JOIN trgm ON trgm.chunk_id = c.id\n" if use_trgm else ""
    )
    trgm_columns = (
        "    trgm.r_trgm,\n    trgm.sim AS trgm_sim"
        if use_trgm
        else "    NULL::integer AS r_trgm,\n    NULL::double precision AS trgm_sim"
    )
    trgm_meta_select = (
        """
    (SELECT COUNT(*) FROM trgm) AS trgm_count,
    (SELECT MIN(sim) FROM trgm) AS trgm_min_sim,
    (SELECT MAX(sim) FROM trgm) AS trgm_max_sim,
    (SELECT AVG(sim) FROM trgm) AS trgm_avg_sim,
"""
        if use_trgm
        else """
    0 AS trgm_count,
    NULL::double precision AS trgm_min_sim,
    NULL::double precision AS trgm_max_sim,
    NULL::double precision AS trgm_avg_sim,
"""
    )
    sql_template = f"""
WITH
params AS (
  SELECT
    websearch_to_tsquery('simple', :q) AS tsq,
    CAST(:q_emb AS vector) AS qvec,
    CAST(:rrf_k AS int) AS rrf_k,
    CAST(:use_doc_filter AS boolean) AS use_doc_filter,
    CAST(:use_fts AS boolean) AS use_fts,
    CAST(:use_trgm AS boolean) AS use_trgm{trgm_threshold_line}
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
){trgm_cte}
, rrf AS (
  SELECT
    src.chunk_id,
    SUM(1.0 / (p.rrf_k + src.rank)) AS score
  FROM (
    SELECT chunk_id, r_fts AS rank FROM fts
    UNION ALL
    SELECT chunk_id, r_vec AS rank FROM vec{trgm_union}
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
{trgm_columns}
  FROM rrf r
  JOIN chunks c ON c.id = r.chunk_id
  JOIN documents d ON d.id = c.document_id
  LEFT JOIN vec ON vec.chunk_id = c.id
  LEFT JOIN fts ON fts.chunk_id = c.id
{trgm_join}  ORDER BY r.score DESC, c.id ASC
  LIMIT :top_k
),
meta AS (
  SELECT
    (SELECT COUNT(*) FROM fts) AS fts_count,
    (SELECT COUNT(*) FROM vec) AS vec_count,
{trgm_meta_select}    (SELECT MIN(dist) FROM vec) AS vec_min_distance,
    (SELECT MAX(dist) FROM vec) AS vec_max_distance,
    (SELECT AVG(dist) FROM vec) AS vec_avg_distance
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
    sql = text(sql_template)
    wants_q_trgm = ":q_trgm" in sql_template or "%(q_trgm)" in sql_template
    bind_params = [
        bindparam("q", type_=String()),
        bindparam("owner_sub", type_=String()),
        bindparam("owner_sub_alt", type_=String()),
        bindparam("q_emb", type_=String()),
        bindparam("rrf_k", type_=Integer()),
        bindparam("use_doc_filter", type_=Boolean()),
        bindparam("use_fts", type_=Boolean()),
        bindparam("use_trgm", type_=Boolean()),
        bindparam("doc_ids", type_=ARRAY(String())),
        bindparam("top_k", type_=Integer()),
        bindparam("fts_k", type_=Integer()),
        bindparam("vec_k", type_=Integer()),
    ]
    if wants_q_trgm:
        bind_params.append(bindparam("q_trgm", type_=String()))
    if use_trgm:
        bind_params.extend(
            [
                bindparam("trgm_limit", type_=String()),
                bindparam("trgm_like_patterns", type_=ARRAY(String())),
                bindparam("trgm_k", type_=Integer()),
            ]
        )
    sql = sql.bindparams(*bind_params)

    exec_params = {
        "owner_sub": owner_sub,
        "owner_sub_alt": owner_sub_alt,
        "q": query_text,
        "q_emb": q_emb,
        "rrf_k": rrf_k,
        "use_doc_filter": use_doc_filter,
        "use_fts": use_fts,
        "use_trgm": use_trgm,
        "doc_ids": doc_ids or [],
        "top_k": top_k,
        "fts_k": fts_k,
        "vec_k": vec_k,
    }
    if wants_q_trgm:
        exec_params["q_trgm"] = q_trgm
    if use_trgm:
        exec_params.update(
            {
                "trgm_limit": f"{float(trgm_limit):.6f}",
                "trgm_like_patterns": trgm_patterns,
                "trgm_k": trgm_k,
            }
        )
    rows = db.execute(sql, exec_params).mappings().all()

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
