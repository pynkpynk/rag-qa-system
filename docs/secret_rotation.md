# Secret Rotation Runbook / シークレットローテーション手順書

## Overview / 概要
- **EN:** This playbook describes which secrets exist in rag-qa-system, when to rotate them, and how to validate the system after rotation.
- **JA:** 本手順書は rag-qa-system で管理すべきシークレット、ローテーションのタイミング、ローテーション後の検証方法をまとめたものです。

## Secret Inventory / シークレット一覧
| Secret (EN) | Location / Usage | シークレット (JA) | 保存先 / 用途 |
| --- | --- | --- | --- |
| OpenAI API Key | FastAPI inference + embeddings | OpenAI API キー | FastAPI からの推論・ベクトル生成 |
| DATABASE_URL | Postgres connection for runs/docs | DATABASE_URL | Postgres 接続 (runs/docs) |
| Auth0 Issuer / Audience / Client secret | Auth mode = auth0 | Auth0 Issuer / Audience / Client secret | AUTH_MODE=auth0 時の認証設定 |
| JWT signing secret (if self-hosted) | Optional | JWT 署名鍵（必要な場合） | 任意の JWT 認証時 |
| AWS credentials (S3 uploads) | Upload pipeline | AWS 認証情報 | S3 アップロード処理 |

## Rotation Triggers / ローテーショントリガー
- **EN:** Incident response, suspected leak, employee offboarding, third-party notification, or scheduled (at least every 90 days).
- **JA:** インシデント対応、漏洩疑い、退職対応、外部通知、または 90 日以内ごとの計画ローテーション。

## Procedures / 手順
### OpenAI API Key / OpenAI API キー
1. **EN:** Generate a new key in the OpenAI console. Update the deployment environment (Render/Vercel env vars) and `backend/.env.local`.  
   **JA:** OpenAI コンソールで新しいキーを発行し、Render/Vercel の環境変数と `backend/.env.local` を更新。
2. **EN:** Restart the worker/API processes.  
   **JA:** API / ワーカーを再起動。
3. **EN:** Run `python scripts/validate_env.py --strict`.  
   **JA:** `python scripts/validate_env.py --strict` を実行。
4. **EN:** Smoke test `/api/health` and one `/api/chat/ask`.  
   **JA:** `/api/health` と `/api/chat/ask` をスモークテスト。

### DATABASE_URL
1. **EN:** Rotate DB password (or create new user) in Postgres. Update DATABASE_URL everywhere.  
   **JA:** Postgres で新パスワード／ユーザーを発行し、各環境の DATABASE_URL を更新。
2. **EN:** Test DB migrations and connections.  
   **JA:** DBマイグレーションと接続テストを実施。

### Auth0 Secrets / Auth0 シークレット
1. **EN:** Rotate client secret or issuer settings in Auth0 dashboard. Ensure `AUTH0_ISSUER`, `AUTH0_AUDIENCE`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` match.  
   **JA:** Auth0 ダッシュボードで client secret / issuer を更新し、環境変数と一致させる。
2. **EN:** Redeploy services; run `validate_env.py`.  
   **JA:** 再デプロイ後に `validate_env.py` を実行。

### AWS Credentials / AWS 認証情報
1. **EN:** Use IAM to create/rotate access keys. Update deployment env vars (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).  
   **JA:** IAMでアクセスキーをローテーションし、環境変数 (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) を更新。
2. **EN:** Run upload smoke (small PDF).  
   **JA:** 小さな PDF でアップロード動作確認。

### JWT Signing Secret / JWT 署名鍵
1. **EN:** Generate new signing key (e.g., `openssl rand -hex 32`).  
   **JA:** `openssl rand -hex 32` などで新しい署名鍵を生成。
2. **EN:** Update env vars (`JWT_SECRET` etc.) and restart auth services.  
   **JA:** 環境変数 (`JWT_SECRET` など) を更新し、認証サービスを再起動。

## Post-Rotation Validation / ローテーション後の検証
- **EN:**  
  1. Run `python scripts/validate_env.py --strict`.  
  2. Hit `/api/health` (expect 200).  
  3. Perform a minimal `/api/chat/ask` (dev seeds).  
  4. Tail audit logs to ensure they remain metadata-only (no question text).  
- **JA:**  
  1. `python scripts/validate_env.py --strict` を実行。  
  2. `/api/health` にアクセス (200 を確認)。  
  3. `/api/chat/ask` を最小限実行 (dev seed run を利用)。  
  4. 監査ログがメタデータのみであることを確認。

## Rollback Guidance / ロールバック手順
- **EN:** Keep the previous secret disabled but recoverable for 24h. If new secret fails, switch env vars back, redeploy, and investigate root cause before reattempting rotation.
- **JA:** 新しいシークレットが安定するまで旧キーを 24 時間保持 (無効化した状態)。問題発生時は旧 env を戻し、再度原因を調査してからローテーションをやり直す。

## Incident Notes Template / インシデント記録テンプレ
```
EN:
- Incident ID / Date
- Secret affected
- Detection source
- Actions taken (rotation, validate_env run, smoke tests)
- Outcome + lessons learned

JA:
- インシデントID・日付
- 影響を受けたシークレット
- 検知元
- 実施した対応 (ローテーション, validate_env 実行, スモークテスト)
- 結果と学び
```
