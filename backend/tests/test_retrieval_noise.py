from __future__ import annotations

from app.core.retrieval_noise import (
    filter_noise_candidates,
    is_noise_text,
    should_bypass_noise_filter,
)


def test_is_noise_text_list_of_figures_true():
    text = (
        "List of Figures\n"
        "Fig. 1.... .................. 3\n"
        "Fig. 2.... .................. 5\n"
        "Appendix C. Glossary ......... 26"
    )
    assert is_noise_text(text) is True


def test_is_noise_text_normal_paragraph_false():
    text = (
        "The Cybersecurity Framework (CSF) is designed to help organizations "
        "manage cybersecurity risk by prioritizing safeguards."
    )
    assert is_noise_text(text) is False


def test_is_noise_text_front_matter_true():
    text = (
        "Acknowledgments\n"
        "This publication is available free of charge from https://doi.org/10.6028/NIST.CSWP.\n"
        "National Institute of Standards and Technology (NIST CSWP-080)."
    )
    assert is_noise_text(text) is True


def test_filter_noise_candidates_prefers_good():
    candidates = [
        {"text": "Important summary of risk obligations."},
        {
            "text": "List of Figures\nFig. A .......... 2\nFig. B .......... 4\nIndex .......... 10"
        },
        {"text": "CSF tier 3 requires policies and evidence tracking."},
        {"text": "Risk management workflow description."},
    ]
    filtered = filter_noise_candidates(candidates, "Summarize the obligations", keep=3)
    assert len(filtered) == 3
    texts = [c["text"] for c in filtered]
    assert all("List of Figures" not in t for t in texts)


def test_filter_noise_candidates_bypass_for_toc_question():
    candidates = [
        {"text": "List of Figures\nFig. A .......... 2\nFig. B .......... 4"},
        {"text": "Overview of the CSF implementation steps."},
        {"text": "Index .......... 30"},
    ]
    question = "目次と List of Figures を教えてください。"
    filtered = filter_noise_candidates(candidates, question, keep=2)
    assert filtered == candidates[:2]
    assert should_bypass_noise_filter(question) is True
