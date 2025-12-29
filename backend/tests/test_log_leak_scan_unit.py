from app.core.log_leak_scan import scan_text, format_report, scan_file


def test_scan_text_detects_bearer_header():
    sample = "INFO Authorization: Bearer sk-TESTTOKEN1234567890"
    violations = scan_text(sample)
    assert violations, "Expected violation for bearer header"
    report = format_report(violations)
    assert "bearer_header" in report


def test_scan_text_detects_jwt():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmF}"  # shortened
    violations = scan_text(jwt)
    assert violations, "JWT-like pattern should be detected"


def test_scan_text_detects_three_segment_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
        "TJVA95OrM7E2cBab30RMHrHDcEfxJoZ1pG2aW"
    )
    violations = scan_text(jwt)
    assert violations, "Three segment JWT should be detected"


def test_scan_text_ignores_base64_without_dots():
    sample = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"  # no dot separator
    violations = scan_text(sample)
    assert not violations, "Base64 chunk without dots should not match JWT rule"


def test_scan_file_accepts_string_path(tmp_path):
    sample = "Authorization: Bearer TESTTOKEN1234567890"
    log = tmp_path / "log.txt"
    log.write_text(sample)
    violations = scan_file(str(log))
    assert violations, "scan_file should detect violations from string paths"
