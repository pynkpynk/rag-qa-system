import json
import logging

import app.api.routes.chat as chat


def test_emit_audit_event_logs_json(caplog):
    caplog.set_level(logging.INFO, logger=chat.audit_logger.name)

    chat._emit_audit_event(
        request_id="req-123",
        run_id="run-abc",
        principal_hash="hash123",
        is_admin_user=True,
        debug_requested=True,
        debug_effective=True,
        retrieval_debug_included=True,
        debug_meta_included=False,
        strategy="vector_by_run_admin",
        chunk_count=2,
        status="success",
        error_code=None,
    )

    records = [rec for rec in caplog.records if rec.name == chat.audit_logger.name]
    assert records, "audit logger should emit a record"
    msg = records[-1].getMessage()
    data = json.loads(msg)
    assert data["retrieval_debug_included"] is True
    assert data["debug_meta_included"] is False
    assert "chunk text" not in msg
