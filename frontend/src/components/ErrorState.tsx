import type { ApiError } from "../lib/api";

type CopyItem = { title: string; body: string; hint?: string };

const COPY: Record<string, CopyItem> = {
  RUN_FORBIDDEN: {
    title: "アクセスできません（403）",
    body: "このRunに紐づくトークンが一致しません。共有されたRunリンク/トークンを確認してください。",
    hint: "別Runのトークンを使っていないか、ヘッダ X-Run-Token を再確認。"
  },
  NO_DOCUMENTS: {
    title: "ドキュメントがありません",
    body: "このRunに紐づくPDFが未添付です。まずアップロード/アタッチしてください。"
  },
  INDEX_FAILED: {
    title: "索引の作成に失敗しました",
    body: "PDFの解析や埋め込み生成で失敗しています。reindexを試すか、失敗理由を確認してください。"
  },
  NETWORK_ERROR: {
    title: "サーバに接続できません",
    body: "ネットワークかデプロイ設定の問題の可能性があります。/api/health が200か確認してください。"
  },
  VALIDATION_ERROR: {
    title: "入力に不備があります",
    body: "送信内容の形式が正しくありません。入力内容を確認してください。"
  },
  INTERNAL_ERROR: {
    title: "サーバ側でエラーが発生しました（500）",
    body: "一時的な不具合の可能性があります。時間を置いて再試行してください。"
  },
  UNKNOWN_ERROR: {
    title: "エラーが発生しました",
    body: "予期しないエラーです。時間を置いて再試行してください。"
  }
};

function getSafeString(v: unknown, fallback: string) {
  return typeof v === "string" && v.length > 0 ? v : fallback;
}

export function ErrorState(props: { error: ApiError; onRetry?: () => void }) {
  const code = getSafeString((props.error as any)?.code, "UNKNOWN_ERROR");
  const copy = COPY[code] ?? COPY.UNKNOWN_ERROR;

  const status = (props.error as any)?.status;
  const requestId = (props.error as any)?.requestId;

  return (
    <div style={{ padding: 16, border: "1px solid rgba(255,255,255,0.15)", borderRadius: 12 }}>
      <div style={{ fontSize: 16, fontWeight: 700 }}>{copy.title}</div>
      <div style={{ marginTop: 8, opacity: 0.9 }}>{copy.body}</div>
      {copy.hint ? <div style={{ marginTop: 8, opacity: 0.7 }}>ヒント: {copy.hint}</div> : null}

      <div style={{ marginTop: 12, fontSize: 12, opacity: 0.7 }}>
        {typeof status === "number" ? `status=${status} / ` : ""}
        code={code}
        {typeof requestId === "string" && requestId.length > 0 ? ` / requestId=${requestId}` : ""}
      </div>

      {props.onRetry ? (
        <button style={{ marginTop: 12 }} onClick={props.onRetry}>
          再試行
        </button>
      ) : null}
    </div>
  );
}
