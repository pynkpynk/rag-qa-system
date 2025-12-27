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
    page: int | None
    chunk_index: int
    text: str
    score: float
    rank_fts: int | None
    rank_vec: int | None


def _to_pgvector_literal(emb: Sequence[float]) -> str:
    """
    pgvector のテキスト表現: "[0.1,0.2,...]"
    - ドライバ側のvectorアダプタ登録に依存しない（CASTでvector化する）
    """
    return "[" + ",".join(str(float(x)) for x in emb) + "]"


def hybrid_search_chunks_rrf(
    db: Session,
    *,
    owner_sub: str,
    document_ids: Sequence[str] | None,
    query_text: str,
    query_embedding: Sequence[float],
    top_k: int = 20,
    fts_k: int = 50,
    vec_k: int = 50,
    rrf_k: int = 60,
) -> list[HybridHit]:
    """
    FTS上位(fts_k) と ベクトル上位(vec_k) を取り、RRFで統合して top_k を返す。

    ✅ multi-tenant 安全策:
      - documents.owner_sub = :owner_sub を必ず通す
      - documents.status = 'indexed' も合わせて通す（運用が安定する）

    ✅ document_ids:
      - 空/None の場合: docフィルタなし（owner_sub配下の indexed 全体を検索）
      - 値ありの場合: その doc_id のみを対象に検索
    """
    if not owner_sub:
        raise ValueError("owner_sub is required")
    if not isinstance(query_text, str) or not query_text.strip():
        raise ValueError("query_text must not be empty")
    if not query_embedding:
        raise ValueError("query_embedding must not be empty")

    if top_k <= 0:
        raise ValueError("top_k must be > 0")
    if fts_k <= 0 or vec_k <= 0:
        raise ValueError("fts_k and vec_k must be > 0")
    if rrf_k <= 0:
        raise ValueError("rrf_k must be > 0")

    doc_ids = list(document_ids or [])
    use_doc_filter = bool(doc_ids)

    # vector(1536) に合わせて CAST(:q_emb AS vector) する（ドライバ依存を減らす）
    q_emb = _to_pgvector_literal(query_embedding)

    sql = text(
        """
WITH
params AS (
  SELECT
    websearch_to_tsquery('simple', :q) AS tsq,
    CAST(:q_emb AS vector) AS qvec,
    :rrf_k::int AS rrf_k,
    :use_doc_filter::boolean AS use_doc_filter
),
fts AS (
  SELECT
    c.id AS chunk_id,
    ROW_NUMBER() OVER (
      ORDER BY ts_rank_cd(c.fts, p.tsq) DESC
    ) AS r_fts
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    d.owner_sub = :owner_sub
    AND d.status = 'indexed'
    AND (p.use_doc_filter = false OR c.document_id = ANY(:doc_ids))
    AND c.fts @@ p.tsq
  ORDER BY ts_rank_cd(c.fts, p.tsq) DESC
  LIMIT :fts_k
),
vec AS (
  SELECT
    c.id AS chunk_id,
    ROW_NUMBER() OVER (
      ORDER BY (c.embedding <=> p.qvec) ASC
    ) AS r_vec
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    d.owner_sub = :owner_sub
    AND d.status = 'indexed'
    AND (p.use_doc_filter = false OR c.document_id = ANY(:doc_ids))
  ORDER BY (c.embedding <=> p.qvec) ASC
  LIMIT :vec_k
),
merged AS (
  SELECT
    COALESCE(fts.chunk_id, vec.chunk_id) AS chunk_id,
    fts.r_fts,
    vec.r_vec,
    (CASE WHEN fts.r_fts IS NULL THEN 0.0 ELSE 1.0 / (p.rrf_k + fts.r_fts) END) +
    (CASE WHEN vec.r_vec IS NULL THEN 0.0 ELSE 1.0 / (p.rrf_k + vec.r_vec) END) AS score
  FROM fts
  FULL OUTER JOIN vec ON vec.chunk_id = fts.chunk_id
  CROSS JOIN params p
)
SELECT
  c.id,
  c.document_id,
  c.page,
  c.chunk_index,
  c.text,
  m.score,
  m.r_fts,
  m.r_vec
FROM merged m
JOIN chunks c ON c.id = m.chunk_id
ORDER BY m.score DESC
LIMIT :top_k;
"""
    ).bindparams(
        bindparam("q", type_=String()),
        bindparam("owner_sub", type_=String()),
        bindparam("q_emb", type_=String()),
        bindparam("rrf_k", type_=Integer()),
        bindparam("use_doc_filter", type_=Boolean()),
        bindparam("doc_ids", type_=ARRAY(String())),
        bindparam("top_k", type_=Integer()),
        bindparam("fts_k", type_=Integer()),
        bindparam("vec_k", type_=Integer()),
    )

    rows = (
        db.execute(
            sql,
            {
                "owner_sub": owner_sub,
                "q": query_text,
                "q_emb": q_emb,
                "rrf_k": rrf_k,
                "use_doc_filter": use_doc_filter,
                "doc_ids": doc_ids,
                "top_k": top_k,
                "fts_k": fts_k,
                "vec_k": vec_k,
            },
        )
        .mappings()
        .all()
    )

    hits: list[HybridHit] = []
    for r in rows:
        hits.append(
            HybridHit(
                chunk_id=r["id"],
                document_id=r["document_id"],
                page=r["page"],
                chunk_index=r["chunk_index"],
                text=r["text"],
                score=float(r["score"]),
                rank_fts=(int(r["r_fts"]) if r["r_fts"] is not None else None),
                rank_vec=(int(r["r_vec"]) if r["r_vec"] is not None else None),
            )
        )

    return hits
