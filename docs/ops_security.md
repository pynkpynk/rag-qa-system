# Operations & Security Policy v0.1
_Last updated: 2025-12-28_

## Quick Summary (EN)
This document defines how to operate **rag-qa-system** safely with minimal leakage risk.
Key guarantees today:
- **Prod debug clamp**: request payload debug is forced OFF in prod unless explicitly allowed.
- **Admin-only debug payloads**: `retrieval_debug` / `debug_meta` never include raw question/chunk text.
- **Metadata-only audit logs**: single-line JSON, includes inclusion flags, never raw content.
- **Owner-based access control**: runs/documents are scoped by `owner_sub` and enforced server-side.
- **Dev seeding is idempotent**: repeated dev seed does not duplicate documents/chunks.
- **Automated log leak scanner**: CI/pytest fails if runtime logs contain forbidden tokens/secrets/raw markers.
- **Secure-by-default middleware**: request IDs, security headers, body-size limits, optional rate limiting for `/api/chat/ask`.

## クイック要約（JA）
この文書は **rag-qa-system** を「漏えいリスク最小」で運用するための方針です。
現時点の主要な安全保証：
- **本番デバッグクランプ**：prodでは明示許可がない限り debug は強制OFF
- **管理者のみデバッグ情報**：`retrieval_debug` / `debug_meta` は raw な質問/チャンク本文を含まない
- **監査ログはメタデータのみ**：1行JSON、含有フラグあり、本文は出さない
- **所有者ベースのアクセス制御**：`owner_sub` による run/doc スコープをサーバ側で強制
- **dev seed は冪等**：繰り返し実行しても重複生成しない
- **ログ漏えいスキャナ**：pytest/CI で禁止トークン・シークレット混入を即検知
- **ミドルウェア防御**：リクエストID、セキュリティヘッダー、ボディサイズ制限、`/api/chat/ask` 向けレート制限（任意）

---

## Table of Contents (EN)
1. Scope & Non-goals  
2. Definitions  
3. Threat Model (LLM/RAG-specific)  
4. Data Classification & Retention  
5. Environment Policy & Debug Controls  
6. Secrets Handling  
7. Audit Logging Policy  
8. Access Control Policy  
9. Incident Response & Break-glass  
10. Release Checklist  
11. Roadmap Backlog (Operational Must-haves / Nice-to-have)  
12. Implemented (Current)

## 目次（JA）
1. 適用範囲と非対象  
2. 用語定義  
3. 脅威モデル（LLM/RAG特有）  
4. データ分類と保持  
5. 環境別方針とデバッグ制御  
6. シークレット管理  
7. 監査ログ方針  
8. アクセス制御方針  
9. インシデント対応・ブレークグラス  
10. リリースチェックリスト  
11. 実装ロードマップ（必須 / あると強い）  
12. 実装済み事項

---

## 1) Scope & Non-goals (EN)
**Scope**
- Applies to rag-qa-system backend: FastAPI API, RAG retrieval pipeline, dev scripts, and operational configuration.
- Focus: environment separation, data handling, access control, debug gating, auditing, incident response.

**Non-goals**
- Frontend UX and UI policy.
- Corporate-wide IT/security governance beyond this repo.
- Upstream document governance prior to ingestion (handled elsewhere).

## 1) 適用範囲と非対象（JA）
**適用範囲**
- rag-qa-system バックエンド全体（FastAPI API、RAG検索、開発スクリプト、運用設定）が対象。
- 主眼：環境分離、データ管理、アクセス制御、デバッグ制御、監査、インシデント対応。

**非対象**
- フロントエンドUX/画面設計。
- 企業ITポリシー全体の定義（このリポジトリ外）。
- 取り込み前のドキュメントガバナンス（別枠で扱う）。

---

## 2) Definitions (EN)
| Term | Meaning |
|---|---|
| `owner_sub` | Principal identifier that owns runs/documents (per-user scope key). |
| `run_id` | A logical query session/collection scope used for retrieval and answering. |
| `payload.debug` | Client request flag that *requests* debug info (not guaranteed). |
| `retrieval_debug` | Admin-only response payload (sanitized) about retrieval strategy/stats. |
| `debug_meta` | Admin-only response payload (sanitized) about internal metadata for debugging. |
| **Prod clamp** | Behavior that forces `payload.debug=False` in prod unless explicitly allowed. |
| **Audit event** | One-line JSON record with metadata only (no raw text). |

## 2) 用語定義（JA）
| 用語               | 意味                                                         |
|-------------------|--------------------------------------------------------------|
| `owner_sub`.      | run/doc の所有者を示す principal 識別子（ユーザー単位のスコープキー） |
| `run_id`          | 検索・回答に使う論理的な実行単位（セッション/コレクション）            |
| `payload.debug`   | クライアントがデバッグ情報を「要求」するフラグ（返るとは限らない）       |
| `retrieval_debug` | 管理者のみのレスポンス情報（サニタイズ済みの検索戦略/統計）             |
| `debug_meta`      | 管理者のみのレスポンス情報（サニタイズ済みの内部メタ）                 |
| **本番クランプ**    | prodで `payload.debug=False` を強制する挙動（例外は明示許可のみ）   |
| **監査イベント**    | メタデータのみの1行JSONログ（本文は出さない）                        |

---

## 3) Threat Model (LLM/RAG-specific) (EN)
We prioritize threats that cause **data leakage** or **cross-tenant access**.

### Primary threats
- **IDOR**: guessing or reusing `run_id` / `document_id` to access other users’ data.
- **Debug leakage**: raw question text, retrieved chunks, or prompt templates leaking via debug endpoints/payloads.
- **Secret exfiltration**: tokens/keys in logs, responses, or developer tooling output.
- **Prompt injection / instruction hijack**: retrieved text attempting to override system behavior.
- **Admin token compromise**: misuse of admin privileges or debug capabilities.

### Security posture
- Default deny for cross-owner access.
- Never log raw sensitive content (questions/chunks/prompts).
- Debug is treated as a *controlled capability*, not a convenience.

## 3) 脅威モデル（LLM/RAG特有）（JA）
最優先は **漏えい** と **テナント越境** を防ぐこと。

### 主要脅威
- **IDOR**：`run_id` / `document_id` の推測・流用による他ユーザー情報へのアクセス
- **デバッグ経由の漏えい**：質問本文/取得チャンク/プロンプトが debug で露出
- **シークレット流出**：ログやレスポンス、開発ツール出力にトークン/キーが混入
- **プロンプトインジェクション**：取得テキストが挙動を乗っ取ろうとする
- **管理者トークン侵害**：debugや権限が悪用される

### 基本姿勢
- 所有者不一致は原則拒否（Default Deny）
- 生テキスト（質問/チャンク/プロンプト）をログに出さない
- debugは「制御された能力」として扱う

---

## 4) Data Classification & Retention (EN)
### Classification
- **Confidential – User scoped**
  - User prompts/questions
  - Retrieved chunks and document text
- **Internal**
  - `request_id`, `run_id`, hashed principal identifier
  - Retrieval strategy and counts (e.g., chunk_count)
  - Inclusion flags (`retrieval_debug_included`, `debug_meta_included`)

### Retention
- Logs: **metadata-only**, retained **30 days** (default).  
- No raw question/chunk/prompt bodies in logs.

### Data handling rules (Do/Don’t)
**Do**
- Hash/normalize principal identifiers in logs.
- Keep debug payloads sanitized and admin-only.

**Don’t**
- Never store or log raw question text or chunk text in application logs.
- Never print tokens/secrets/bearer values.

## 4) データ分類と保持（JA）
### 分類
- **機密（ユーザー単位）**
  - ユーザーの質問/プロンプト
  - 取得チャンク/ドキュメント本文
- **社内限定**
  - `request_id`, `run_id`, principal のハッシュ
  - 検索戦略や件数（chunk_count等）
  - 含有フラグ（`retrieval_debug_included`, `debug_meta_included`）

### 保持
- ログ：**メタデータのみ**、原則 **30日** 保持（デフォルト）  
- 質問/チャンク/プロンプト本文はログに残さない

### 取り扱いルール（Do/Don’t）
**Do**
- principal識別子はハッシュ化して記録
- debug payloadはサニタイズ＆管理者限定

**Don’t**
- アプリログに質問本文/チャンク本文/プロンプト本文を出さない
- トークン/シークレット/bearer値を出さない

---

## 5) Environment Policy & Debug Controls (EN)
### Environment keys
- `APP_ENV`: `dev` / `stage` / `prod`
- `ALLOW_PROD_DEBUG`: `0` / `1` (default: `0`)
- `ENABLE_RETRIEVAL_DEBUG`: feature flag (default: safe/off in prod deployments unless explicitly enabled)
- `RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH`: additional admin/debug gate (recommended for prod)
- Detailed Auth0-specific requirements are documented in [auth0_env.md](auth0_env.md).

### Debug clamp rule (Implemented)
- In **prod** (`APP_ENV=prod`):  
  - `payload.debug` is forced **False** unless `ALLOW_PROD_DEBUG=1`.
- `retrieval_debug` and `debug_meta` remain **admin-only** and **sanitized** in all environments.

### Recommended defaults by environment
| Setting | dev | stage | prod |
|---|---:|---:|---:|
| `ALLOW_PROD_DEBUG` | 1 | 0 (or 1 for controlled staging) | 0 |
| `ENABLE_RETRIEVAL_DEBUG` | 1 | 0/1 (controlled) | 0 (default) |
| `RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH` | 0 | 1 | 1 |
| Logging raw content | Never | Never | Never |

### Baseline middleware protections
- **EN:** Every request carries an `X-Request-ID`; responses echo it for tracing. Security headers (`X-Content-Type-Options`, `Referrer-Policy`, etc.) are set globally. Requests exceeding `MAX_REQUEST_BYTES` (default 1MB dev / 256KB prod) receive HTTP 413. An optional per-IP rate limit protects `POST /api/chat/ask` (disabled in dev by default).  
- **JA:** すべてのリクエストに `X-Request-ID` を付与し、レスポンスでも反映。セキュリティヘッダー（`X-Content-Type-Options` など）を一括適用。`MAX_REQUEST_BYTES`（dev=1MB, prod=256KB）超過はHTTP 413。`POST /api/chat/ask` 向けのIPレート制限を用意（デフォルトはdevで無効）。

## 5) 環境別方針とデバッグ制御（JA）
### 環境キー
- `APP_ENV`: `dev` / `stage` / `prod`
- `ALLOW_PROD_DEBUG`: `0` / `1`（デフォルト `0`）
- `ENABLE_RETRIEVAL_DEBUG`: 機能フラグ（prodは明示ONしない限りOFF推奨）
- `RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH`: 追加の管理者/デバッグゲート（prod推奨）
- Auth0 固有の要件は [auth0_env.md](auth0_env.md) を参照。

### 本番クランプ（実装済）
- **prod**（`APP_ENV=prod`）では：  
  - `ALLOW_PROD_DEBUG=1` でない限り `payload.debug` は強制 **False**
- `retrieval_debug` / `debug_meta` は全環境で **管理者のみ** かつ **サニタイズ**

### 環境別の推奨デフォルト
| 設定 | dev | stage | prod |
|---|---:|---:|---:|
| `ALLOW_PROD_DEBUG` | 1 | 0（または制御下で1） | 0 |
| `ENABLE_RETRIEVAL_DEBUG` | 1 | 0/1（制御） | 0（デフォルト） |
| `RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH` | 0 | 1 | 1 |
| 生本文ログ | 禁止 | 禁止 | 禁止 |

---

## 6) Secrets Handling (EN)
### Rules
- Store secrets only in environment variables or a secrets manager/vault.
- Never commit secrets to git.
- Never print tokens/secrets/bearer values in logs.
- See also: [Secret Rotation Runbook](secret_rotation.md) for detailed procedures.

### Examples (placeholders)
- `OPENAI_API_KEY=***`
- `DATABASE_URL=***`
- `AUTH0_CLIENT_SECRET=***`

## 6) シークレット管理（JA）
### ルール
- シークレットは環境変数または secrets manager/vault のみ
- gitへコミット禁止
- ログにトークン/シークレット/bearer値を絶対に出さない
- 詳細手順は [シークレットローテーション手順書](secret_rotation.md) を参照。

### 例（プレースホルダ）
- `OPENAI_API_KEY=***`
- `DATABASE_URL=***`
- `AUTH0_CLIENT_SECRET=***`

---

## 7) Audit Logging Policy (EN)
### Purpose
Audit logs exist to answer: “What happened?” **without** leaking user content.

### Requirements (Implemented)
- Emit **one JSON line** per event to the audit logger.
- Must include:
  - `request_id`, `run_id` (when available)
  - hashed principal identifier
  - `retrieval_debug_included` / `debug_meta_included`
  - retrieval `strategy` + counts (e.g., `chunk_count`)
  - `app_env`, `status`, optional `error_code`
- Must **never** include:
  - raw question text
  - raw chunk text
  - prompt templates/bodies
  - tokens/secrets

### Reference schema (example)
```json
{
  "event": "chat_ask",
  "app_env": "prod",
  "request_id": "…",
  "run_id": "…",
  "principal_hash": "…",
  "retrieval_debug_included": false,
  "debug_meta_included": false,
  "strategy": "hybrid_rrf_by_run_admin",
  "chunk_count": 12,
  "status": "ok",
  "error_code": null
}
````

## 7) 監査ログ方針（JA）

### 目的

監査ログは「何が起きたか」を追うためのもの。**本文を出さず**に原因追跡できる状態を作る。

### 要件（実装済）

* 監査ロガーに **1行JSON** を出す
* 含めるべき項目：

  * `request_id`, `run_id`（可能なら）
  * principalのハッシュ
  * `retrieval_debug_included` / `debug_meta_included`
  * 検索 `strategy` と件数（`chunk_count`等）
  * `app_env`, `status`, （必要なら）`error_code`
* 含めてはいけない項目：

  * 質問本文
  * チャンク本文
  * プロンプト本文/テンプレ
  * トークン/シークレット

### 参考スキーマ（例）

```json
{
  "event": "chat_ask",
  "app_env": "prod",
  "request_id": "…",
  "run_id": "…",
  "principal_hash": "…",
  "retrieval_debug_included": false,
  "debug_meta_included": false,
  "strategy": "hybrid_rrf_by_run_admin",
  "chunk_count": 12,
  "status": "ok",
  "error_code": null
}
```

---

## 8) Access Control Policy (EN)

### Ownership rules

* Each run/document is owned by `owner_sub`.
* Non-admin callers must match ownership to access run-scoped retrieval.

### Enforcement (Implemented)

* `ensure_run_access` enforces owner checks.
* `/api/chat/ask` verifies run ownership before retrieval.
* Cross-user run access returns **404** (avoid existence oracle).

### Admin overrides

* Admin privileges must be explicit and gated (allowlists and/or token-hash gates recommended in prod).

## 8) アクセス制御方針（JA）

### 所有者ルール

* run/doc は `owner_sub` に紐づく
* 非管理者は owner一致時のみアクセス可能

### 強制（実装済）

* `ensure_run_access` による所有者チェック
* `/api/chat/ask` は検索前に run 所有を確認
* 越境アクセスは **404**（存在オラクルを避ける）

### 管理者権限

* 明示的かつ追加ゲート必須（prodでは allowlist / token-hash 等を推奨）

---

## 9) Incident Response & Break-glass (EN)

### When to trigger

* Audit anomalies (unexpected env, missing hashes, unusual spike in denied access).
* Suspected leakage or unauthorized access.

### Steps

1. **Contain**: disable debug features (`ALLOW_PROD_DEBUG=0`, disable retrieval debug flags).
2. **Investigate** using audit stream (metadata-only) and infrastructure logs.
3. **Rotate** secrets and revoke tokens.
4. **Verify** by re-running full regression tests and smoke checks.
5. **Document** incident: timeline, impact, root cause, remediation.

### Break-glass principle

* Only use debug in isolated instances. Keep prod clamp active unless explicitly approved.

## 9) インシデント対応・ブレークグラス（JA）

### 発動条件

* 監査ログの異常（想定外環境、ハッシュ欠落、拒否の急増など）
* 漏えい/不正アクセスの疑い

### 手順

1. **封じ込め**：debug系を停止（`ALLOW_PROD_DEBUG=0`、関連フラグOFF）
2. **調査**：監査ストリーム（メタデータ）＋基盤ログで原因追跡
3. **ローテーション**：シークレット更新、トークン失効
4. **検証**：回帰テスト＋スモークで再発防止を確認
5. **記録**：タイムライン、影響範囲、原因、恒久対策を残す

### ブレークグラス原則

* debugは隔離環境でのみ使う。prodクランプは原則維持。

---

## 10) Release Checklist (EN)

| Item                      | Acceptance                                                                                      |
| ------------------------- | ----------------------------------------------------------------------------------------------- |
| Prod debug clamp verified | In `APP_ENV=prod` with `ALLOW_PROD_DEBUG=0`, responses omit `retrieval_debug` and `debug_meta`. |
| Full test suite           | `python -m pytest -q` passes.                                                                   |
| Audit schema              | Audit JSON lines include inclusion flags and contain no raw question/chunk strings.             |
| Secrets hygiene           | No secrets committed; secrets stored only in env/vault.                                         |
| Access control regression | Cross-owner run access returns 404; owner access works.                                         |
| Env validation script     | `python scripts/validate_env.py --strict` passes.                                               |
| Middleware hardening      | Verify `X-Request-ID` echo, security headers, HTTP 413 (oversized) & 429 (rate limit) responses. |
| RC smoke run              | `backend/scripts/smoke.sh` (or `scripts/smoke.sh rc`) succeeds in target environment.           |
> See [auth0_env.md](auth0_env.md) for Auth0 variable expectations and [release_rc_checklist.md](release_rc_checklist.md) for RC workflow.

Additional release runbook: see [release_rc_checklist.md](release_rc_checklist.md) for an end-to-end RC workflow (English & Japanese).

## 10) リリースチェックリスト（JA）

| 項目           | 受入条件                                                                              |
| --------------| -------------------------------------------------------------------------------------|
| 本番クランプ確認 | `APP_ENV=prod` かつ `ALLOW_PROD_DEBUG=0` で `retrieval_debug` / `debug_meta` が返らない |
| テスト全通      | `python -m pytest -q` が成功                                                          |
| 監査スキーマ    | inclusionフラグ入りJSONが出て、質問/チャンク本文が混入しない                                 |
| シークレット衛生 | シークレットがコミットされていない／env/vaultのみ                                           |
| アクセス制御回帰 | owner不一致は404、owner一致は正常                                                       |
| 環境検証スクリプト | `python scripts/validate_env.py --strict` が成功                                         |
| ミドルウェア検証 | `X-Request-ID` ヘッダー、セキュリティヘッダー、HTTP 413/429（レート制限）を確認               |
> Auth0 関連の詳細要件は [auth0_env.md](auth0_env.md) を参照。
RC全体の手順については [release_rc_checklist.md](release_rc_checklist.md) を確認。

包括的なリリース手順については [release_rc_checklist.md](release_rc_checklist.md) を参照。

---

## 11) Roadmap Backlog (EN)

### Operational Must-haves
1. **Phase 2 – RC automation & smoke**  
   Acceptance: release RC checklist + smoke script executed before staging promotion.
2. **Phase 2 – Secret rotation discipline**  
   Acceptance: [secret_rotation.md](secret_rotation.md) runbook exercised in staging, evidence captured.
3. **Phase 3 – Real-time audit anomaly detection**  
   Acceptance: streaming alerts within 5 min for defined anomalies in prod logs.

### Nice-to-have (Strong)
1. **Phase 2 – Differential privacy metrics**  
   Acceptance: optional DP mode available, documented trade-offs/tests.
2. **Phase 3 – Access-control SQL lint**  
   Acceptance: automated static analysis & checklist in PR workflow.
3. **Phase 3 – Auto-expiring debug tokens**  
   Acceptance: debug enablement requires time-limited token + approval log.

## 11) 実装ロードマップ（JA）

### 運用必須（Must-haves）
1. **フェーズ2 – RC自動化＆スモーク**  
   受入条件：リリースRCチェックリストとスモークスクリプトをステージング昇格前に実施。
2. **フェーズ2 – シークレットローテーション徹底**  
   受入条件：[secret_rotation.md](secret_rotation.md) の手順をステージングで検証済み、証跡あり。
3. **フェーズ3 – 監査異常のリアルタイム検知**  
   受入条件：定義した異常が発生から5分以内にアラートされる仕組み。

### あると強い（Nice-to-have）
1. **フェーズ2 – DPメトリクス**  
   受入条件：差分プライバシー付き集計がオプションで利用可能、トレードオフとテストが整備済み。
2. **フェーズ3 – アクセス制御SQLの静的解析**  
   受入条件：PRワークフローで自動チェックと確認リストを運用。
3. **フェーズ3 – debugトークンの自動失効＋承認**  
   受入条件：時間制限付きの debug 有効化と承認ログが残る。

---

## 12) Implemented (Current) (EN)

* Prod debug clamp: `payload.debug` forced off unless `ALLOW_PROD_DEBUG=1` in prod.
* Admin-only `retrieval_debug` / `debug_meta` with sanitized payloads (no raw question/chunk text).
* Audit logger emits metadata-only JSON including:

  * `retrieval_debug_included` / `debug_meta_included`
  * hashed principal identifier
* Owner enforcement via `ensure_run_access` and run-scoped checks in `/api/chat/ask`.
* Dev seed script idempotency (documents reused by `content_hash`, chunks created once).
* Regression tests for guardrails, audit logging, **log leak scanner**, and middleware hardening (request ID, headers, 413/429).

## 12) 実装済み事項（JA）

* 本番クランプ：prodで `ALLOW_PROD_DEBUG=1` でない限り `payload.debug` を強制OFF
* `retrieval_debug` / `debug_meta` は管理者のみ＆サニタイズ（質問/チャンク本文なし）
* 監査ロガー：メタデータのみのJSONを出力

  * `retrieval_debug_included` / `debug_meta_included`
  * principalはハッシュ化
* `ensure_run_access` と `/api/chat/ask` による所有者チェック
* dev seed の冪等化（`content_hash` で再利用、chunkは重複生成しない）
* ガードレール/監査ログ/ログ漏えいスキャナ/ミドルウェア硬化の回帰テスト

```

---

## 進捗（公開ゴール基準）
このタスク（Phase1: v0.1仕様書の“読みやすい版”確定）で、**40% → 45%** くらいまで進んだ感覚。  
次の伸びしろは **本番Auth0/JWT運用＋レート制限＋監視/アラート** あたりが大きい。

---

この「ops_security.mdの整形テンプレ」を **Prompt Vault** に保存しておく？（YES/NO）
::contentReference[oaicite:0]{index=0}
```
