import re
from typing import Iterable

INJECTION_PATTERNS = [
    r"ignore (all|previous) instructions",
    r"system prompt",
    r"developer message",
    r"you are chatgpt",
    r"exfiltrate",
    r"leak",
    r"secret",
    r"password",
    r"api[_-]?key",
    r"BEGIN\s+(SYSTEM|DEVELOPER|PROMPT)",
    r"あなたは.*(従え|無視しろ|命令)",
]

_inj_re = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

def guard_source_text(text: str) -> str:
    """
    Wrap sources as 'UNTRUSTED QUOTE' and neutralize instruction-like lines.
    """
    lines = text.splitlines()
    out_lines = []
    for ln in lines:
        if _inj_re.search(ln):
            out_lines.append("[[POTENTIAL_INJECTION_REDACTED_LINE]]")
        else:
            out_lines.append(ln)
    return "\n".join(out_lines)

def guard_sources_texts(texts: Iterable[str]) -> list[str]:
    return [guard_source_text(t) for t in texts]
