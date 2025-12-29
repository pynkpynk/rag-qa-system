# Release Candidate Checklist / リリース候補チェックリスト

## 1. Title & Purpose / 目的
**EN:** This checklist ensures every rag-qa-system backend build deemed “Release Candidate (RC)” is validated for functionality, security, and operations prior to deployment.

**JA:** 本チェックリストは、rag-qa-system バックエンドのビルドを RC と見なす前に、機能・セキュリティ・運用の観点で検証するためのものです。

## 2. Preconditions / 事前条件
**EN:**
- Python 3.12+ with virtualenv activated.
- `pip install -r backend/requirements-dev.txt` completed.
- Environment variables loaded via `backend/.env.local` (no secrets printed).
- curl available (jq optional; script falls back to grep).

**JA:**
- Python 3.12 以上＋仮想環境を有効化済み。
- `pip install -r backend/requirements-dev.txt` 実行済み。
- `backend/.env.local` で環境変数を読み込む（秘密値は表示しない）。
- curl が利用可能（jq は任意、無い場合は grep で代替）。

## 3. Local RC Steps / ローカルRC手順
**EN:**
1. `cd backend`
2. `python -m pytest -q`
3. `python scripts/validate_env.py --strict`
4. `bash scripts/smoke.sh` (set RUN_ID if available)
   - Expect `/api/health` HTTP 200
   - Expect `/api/chat/ask` success in dev; check prod clamp if APP_ENV=prod
5. Review `.pytest_logs/pytest.log` for forbidden pattern failures (should be none)

**JA:**
1. `cd backend`
2. `python -m pytest -q`
3. `python scripts/validate_env.py --strict`
4. `bash backend/scripts/smoke.sh` または `bash scripts/smoke.sh rc`（RUN_ID があれば指定）
   - `/api/health` が 200
   - dev で `/api/chat/ask` が成功、APP_ENV=prod ならクランプ動作を確認
5. `.pytest_logs/pytest.log` に禁止パターン検出 (FAIL) が無いことを確認

## 4. Deployment RC Steps / デプロイRC手順
**EN:**
1. Ensure GitHub Actions `backend_ci` succeeded for the RC branch.
2. Deploy to staging (same env vars as prod, secrets swapped).
3. Run `scripts/smoke.sh BASE_URL=https://staging-host`.
4. Perform targeted tests (e.g., `pytest -q tests/test_chat_guardrails.py`).

**JA:**
1. RC ブランチで GitHub Actions `backend_ci` が成功していること。
2. ステージングへデプロイ（prod と同じ env、秘密値のみ差し替え）。
3. `backend/scripts/smoke.sh BASE_URL=https://staging-host` または `scripts/smoke.sh rc BASE_URL=...` を実行。
4. 重点テスト（例：`pytest -q tests/test_chat_guardrails.py`）を実施。

## 5. Prod Clamp Verification / 本番クランプ検証
**EN:** With `APP_ENV=prod` and `ALLOW_PROD_DEBUG=0`, send `/api/chat/ask` payload including `"debug": true`. Response MUST omit `retrieval_debug` and `debug_meta`. Example command lives in `scripts/smoke.sh` and should log success/failure.

**JA:** `APP_ENV=prod`, `ALLOW_PROD_DEBUG=0` 状態で `"debug": true` を含む `/api/chat/ask` を送信し、`retrieval_debug` / `debug_meta` が返らないこと。`scripts/smoke.sh` の検証で成功/失敗を記録する。

## 6. Log Leak Scan Verification / ログ漏えいスキャナ確認
**EN:** `pytest` captures logs into `.pytest_logs/pytest.log` and runs `log_leak_scan` after the session. If forbidden data appears, pytest fails with “Forbidden patterns detected…”. Ensure the RC run shows no such failures.

**JA:** `pytest` 実行時に `.pytest_logs/pytest.log` にログを集約し、終了時に `log_leak_scan` を実行。禁止パターンが検出されると “Forbidden patterns detected…” で失敗するので、RC ではそのような失敗が無いことを確認。

## 7. Auth0 Mode Sanity Checks / Auth0 モード確認
**EN:** Follow [auth0_env.md](auth0_env.md). Validate that:
- `AUTH0_ISSUER` or `AUTH0_DOMAIN` set correctly (`https://tenant/`).
- `AUTH0_AUDIENCE` matches API Identifier.
- `python scripts/validate_env.py --strict` succeeds with AUTH_MODE=auth0.

**JA:** [auth0_env.md](auth0_env.md) に従い、以下を確認：
- `AUTH0_ISSUER` または `AUTH0_DOMAIN` が正しく設定 (`https://tenant/` 形式)。
- `AUTH0_AUDIENCE` が API Identifier と一致。
- `python scripts/validate_env.py --strict` が AUTH_MODE=auth0 で成功。

## 8. Rollback Steps / ロールバック手順
**EN:**
1. Revert infrastructure to previous RC build.
2. If secrets rotated, follow [secret_rotation.md](secret_rotation.md) to restore prior values (keep temporary key valid for 24h).
3. Disable new traffic (load balancer or feature flag) until root cause is resolved.
4. Document incident + resolution in ops log.

**JA:**
1. インフラを直前の RC ビルドへ戻す。
2. シークレットをローテーションした場合は [secret_rotation.md](secret_rotation.md) を参照して旧値に戻す（旧キーは24時間保持）。
3. 原因が解決するまで新規トラフィックを停止（LB やフラグで制御）。
4. インシデントの経緯と対処を ops ログに記録。

## 9. Troubleshooting / トラブルシューティング
**EN:**
- `validate_env` fails on Auth0 audience → ensure Identifier matches and rerun.
- Smoke script reports prod clamp failure → verify `ALLOW_PROD_DEBUG` and redeploy.
- 413 check skipped → ensure MAX_REQUEST_BYTES is exported before smoke run.
- Rate limit assertions skipped → set `RATE_LIMIT_ENABLED=1` + `RATE_LIMIT_RPM` before smoke.

**JA:**
- `validate_env` が Auth0 audience で失敗 → Identifier が一致しているか確認し再実行。
- スモークで本番クランプ失敗 → `ALLOW_PROD_DEBUG` を確認し、必要なら再デプロイ。
- 413 チェックがスキップされる → スモーク実行前に MAX_REQUEST_BYTES を設定。
- レート制限テストがスキップされる → `RATE_LIMIT_ENABLED=1` と `RATE_LIMIT_RPM` を事前に設定。
