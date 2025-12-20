-- pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 例：runs に token_hash を足す（既にrunsがある前提）
ALTER TABLE runs
ADD COLUMN IF NOT EXISTS token_hash TEXT;

-- 例：documents に storage情報を足す（既にdocumentsがある前提）
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS storage_path TEXT,
ADD COLUMN IF NOT EXISTS storage_key TEXT;

-- 索引用ジョブテーブル（無ければ作る）
CREATE TABLE IF NOT EXISTS index_jobs (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL,
  doc_id UUID NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
  attempt_count INT NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_index_jobs_status ON index_jobs(status);
CREATE INDEX IF NOT EXISTS idx_index_jobs_run_doc ON index_jobs(run_id, doc_id);
