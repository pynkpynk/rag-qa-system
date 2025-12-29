from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# ----------------------------
# Text cleaning
# ----------------------------
_RE_HEADER = re.compile(r"^\s*SID\s+WID\s+text_to_write\s*$", re.IGNORECASE)
_RE_LEADING_NUM_COLS = re.compile(r"^\s*\d+\s+\d+\s+")
_RE_LICENSE_LINE = re.compile(r"^\s*Licensed to Google for training use only\.\s*$", re.IGNORECASE)


def clean_chunk_text(raw: str) -> str:
    """
    Conservative cleanup:
    - drop obvious CSV header lines
    - drop "Licensed to Google..." boilerplate line
    - remove leading numeric columns like "159 23 " when line looks like a row
    - normalize newlines and trim excess blank lines

    NOTE: This is intentionally conservative to avoid destroying content.
    """
    if raw is None:
        return ""

    s = raw.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\x00", "")  # NUL guard

    lines = []
    for ln in s.split("\n"):
        ln_stripped = ln.strip()

        if not ln_stripped:
            lines.append("")
            continue

        if _RE_HEADER.match(ln_stripped):
            # drop CSV header
            continue

        if _RE_LICENSE_LINE.match(ln_stripped):
            # drop boilerplate
            continue

        # remove leading numeric columns (common in exported tables)
        ln2 = _RE_LEADING_NUM_COLS.sub("", ln_stripped)

        lines.append(ln2)

    # collapse excessive blank lines
    out_lines = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                out_lines.append("")
        else:
            blank_run = 0
            out_lines.append(ln)

    return "\n".join(out_lines).strip()


def _to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.10f}" for x in vec) + "]"


def embed_text(text_in: str) -> list[float]:
    api_key = os.getenv("OPENAI_API_KEY") or ""
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small"

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=model, input=text_in)
    emb = resp.data[0].embedding
    if not isinstance(emb, list) or not emb:
        raise RuntimeError("Embedding response is empty")
    return emb


@dataclass
class Row:
    chunk_id: str
    text: str


def iter_chunks(session, owner_sub: Optional[str], limit: int) -> Iterable[Row]:
    q = """
    SELECT c.id::text AS chunk_id, c.text AS text
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE (:owner_sub IS NULL OR d.owner_sub = :owner_sub)
    ORDER BY c.id
    LIMIT :limit
    """
    rows = session.execute(text(q), {"owner_sub": owner_sub, "limit": limit}).mappings().all()
    for r in rows:
        yield Row(chunk_id=r["chunk_id"], text=r["text"] or "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner-sub", default=None, help="Filter by documents.owner_sub (e.g. auth0|xxxx). Omit to target all.")
    ap.add_argument("--limit", type=int, default=100000, help="Max chunks to scan")
    ap.add_argument("--dry-run", action="store_true", help="Do not write updates; just report")
    ap.add_argument("--apply", action="store_true", help="Write updates to DB")
    ap.add_argument("--reembed", action="store_true", help="Recompute embeddings for changed chunks (costs tokens)")
    ap.add_argument("--print-samples", type=int, default=3, help="Print N sample before/after pairs")
    args = ap.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("Choose only one: --dry-run or --apply")

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is not set")

    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)

    changed = 0
    scanned = 0
    printed = 0

    with SessionLocal() as session:
        for row in iter_chunks(session, args.owner_sub, args.limit):
            scanned += 1
            cleaned = clean_chunk_text(row.text)

            if cleaned == row.text.strip():
                continue

            changed += 1
            if printed < args.print_samples:
                print("---- CHUNK", row.chunk_id, "----")
                print("[BEFORE]\n", row.text[:800])
                print("\n[AFTER]\n", cleaned[:800])
                print("--------------\n")
                printed += 1

            if args.apply:
                if args.reembed:
                    emb = embed_text(cleaned)
                    emb_lit = _to_pgvector_literal(emb)
                    session.execute(
                        text("UPDATE chunks SET text=:t, embedding=CAST(:e AS vector) WHERE id=CAST(:id AS uuid)"),
                        {"t": cleaned, "e": emb_lit, "id": row.chunk_id},
                    )
                else:
                    session.execute(
                        text("UPDATE chunks SET text=:t WHERE id=CAST(:id AS uuid)"),
                        {"t": cleaned, "id": row.chunk_id},
                    )

                # commit in small batches
                if changed % 50 == 0:
                    session.commit()

        if args.apply:
            session.commit()

    print(f"scanned={scanned} changed={changed} mode={'APPLY' if args.apply else 'DRY-RUN'} reembed={args.reembed}")


if __name__ == "__main__":
    main()
