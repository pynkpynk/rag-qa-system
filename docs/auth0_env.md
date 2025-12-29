# Auth0 Environment Guide / Auth0 環境ガイド

## Overview / 概要
- **EN:** This guide explains which environment variables are required when `AUTH_MODE=auth0`, how to configure AUTH0_DOMAIN vs AUTH0_ISSUER, what AUTH0_AUDIENCE means, and how `validate_env.py` enforces these rules.
- **JA:** このガイドは `AUTH_MODE=auth0` 時に必要な環境変数、AUTH0_DOMAIN と AUTH0_ISSUER の扱い、AUTH0_AUDIENCE の意味、そして `validate_env.py` による検証内容を説明します。

## Required Variables by Mode / モード別必須変数
| Mode | Required Vars (EN) | 必須変数（JA） |
| --- | --- | --- |
| `AUTH_MODE=dev` | `DATABASE_URL`, `OPENAI_API_KEY` (Auth0 vars optional) | `DATABASE_URL`, `OPENAI_API_KEY`（Auth0 関連は任意） |
| `AUTH_MODE=auth0` | `DATABASE_URL`, `OPENAI_API_KEY`, **Auth0 trio**:<br> - `AUTH0_ISSUER` (preferred) or `AUTH0_DOMAIN`<br> - `AUTH0_AUDIENCE` (API Identifier)<br> - Optional client credentials (if using client credentials flow) | `DATABASE_URL`, `OPENAI_API_KEY`, **Auth0 3要素**:<br> - `AUTH0_ISSUER`（推奨）または `AUTH0_DOMAIN`<br> - `AUTH0_AUDIENCE`（API Identifier）<br> - 必要に応じて client credentials |

## AUTH0_DOMAIN vs AUTH0_ISSUER
- **EN:**  
  - `AUTH0_ISSUER` should be the canonical HTTPS URL ending with `/`, e.g. `https://your-tenant.us.auth0.com/`.  
  - If only `AUTH0_DOMAIN` is provided (e.g. `your-tenant.us.auth0.com`), the application derives `AUTH0_ISSUER = https://<domain>/`.  
  - Providing both is allowed; issuer takes precedence.
- **JA:**  
  - `AUTH0_ISSUER` は末尾 `/` を含む HTTPS URL（例: `https://your-tenant.us.auth0.com/`）。  
  - `AUTH0_DOMAIN` のみを指定した場合（例: `your-tenant.us.auth0.com`）、アプリ側で `AUTH0_ISSUER` を補完する。  
  - 両方指定しても問題なし。優先されるのは `AUTH0_ISSUER`。

## AUTH0_AUDIENCE Meaning / AUTH0_AUDIENCE の意味
- **EN:**  
  - Represents the **API Identifier** for your Auth0 API (the value tokens use in the `aud` claim).  
  - Typical formats: `https://api.example.com` or `urn:my-api`.  
  - Configure it under Auth0 Dashboard → APIs → (Your API) → Identifier.  
  - `validate_env.py` will fail with an actionable message if this value is missing.
- **JA:**  
  - Auth0 API の **API Identifier**（アクセストークンの `aud` クレームに入る値）。  
  - 形式例: `https://api.example.com` や `urn:my-api`。  
  - Auth0 ダッシュボード → APIs → 対象API → Identifier で設定する。  
  - `validate_env.py` は未設定の場合にヒント付きで失敗する。

## Common Misconfigurations / ありがちな設定ミス
| Issue (EN) | How `validate_env.py` helps | 説明（JA） |
| --- | --- | --- |
| Missing `AUTH0_AUDIENCE` | Prints “AUTH0_AUDIENCE missing. Set to Auth0 API Identifier…” with steps. | `AUTH0_AUDIENCE` 未設定 → 「API Identifier を設定」とヒント付きで失敗 |
| `AUTH0_ISSUER` missing slash | Fails with “must start with https:// and end with '/'”. | 末尾 `/` が無い → エラーメッセージで指摘 |
| Using prod without prod clamps | Prod step of `validate_env.py --strict` ensures `ALLOW_PROD_DEBUG=0`. | prod で clamp が緩んでいると警告/失敗 |

## Security Notes / セキュリティ注意事項
- **EN:**  
  - Never log Auth0 tokens or decoded payloads in application logs.  
  - Rotate Auth0 client secrets using the [Secret Rotation Runbook](secret_rotation.md).  
  - Treat admin/debug tokens as short-lived and keep them out of shared channels.
- **JA:**  
  - Auth0 トークンやデコード結果をアプリログに出力しない。  
  - Auth0 client secret は [シークレットローテーション手順書](secret_rotation.md) に従って更新。  
  - 管理者/デバッグトークンは短期利用に留め、共有チャンネルへ流出させない。

## Related References / 関連情報
- `docs/ops_security.md` – environment policy, debug clamp, release checklist.
- `backend/scripts/validate_env.py` – automated validation CLI (run with `--strict` before release).
- `backend/tests/test_validate_env.py` – regression tests ensuring validation remains strict but informative.
