from app.api.routes.chat import has_ambiguous_reference, normalize_bullets, is_generic_query

def test_ambiguous_reference_detection():
    assert has_ambiguous_reference("このPDFは何？") is True
    assert has_ambiguous_reference("上記の内容を要約して") is True
    assert has_ambiguous_reference("それを説明して") is True
    assert has_ambiguous_reference("Same_Project_Different_Perspectives_PMI.pdf を要約して") is False
    assert has_ambiguous_reference("この問題を解決して") is True  # ※「これ」は厳しめ判定。必要なら調整。

def test_normalize_bullets_single_line_to_multiline():
    src = "- A[S1 p.1]. - B[S2 p.2]. - C[S3 p.3]."
    out = normalize_bullets(src)
    assert "\n- B" in out
    assert out.startswith("- ")

def test_generic_query_gate():
    assert is_generic_query("テスト") is True
    assert is_generic_query("test") is True
    assert is_generic_query("RAGのテスト方法を教えて") is False
