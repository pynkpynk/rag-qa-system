# Debug/Health Response Allowlist

This document freezes which fields may appear in debug/health payloads returned by production APIs.

## /api/search (debug=true)
Allowed fields within `debug`:
- `used_mode`
- `doc_filter_reason`
- `fts_count`
- `vec_count`
- `trgm_count`
- `trgm_enabled`
- `vec_min_distance`
- `vec_max_distance`
- `vec_avg_distance`
- `trgm_min_sim`
- `trgm_max_sim`
- `trgm_avg_sim`
- `used_min_score`
- `used_max_vec_distance`
- `used_use_doc_filter`
- `used_k_trgm`
- `used_trgm_limit`

All other keys (especially anything revealing principals or DB host info) must remain absent.

## /api/chat/ask (debug=true)
- Debug payload remains empty in production.

## /api/chunks/health
Allowed top-level keys:
- `ok`
- `db` (and its existing nested fields: dialect/alembic info/index booleans)

Forbidden keys:
- Any `principal_sub`/`owner_sub*`
- Any `db_*` outside the `db` object
