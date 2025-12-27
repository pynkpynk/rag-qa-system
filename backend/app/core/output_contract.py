import re

# Allow only whitespace + [S<number>] tokens
_ALLOWED = re.compile(r"^\s*(\[\s*S\d+\s*\]\s*)+\s*$")

def assert_citation_contract(text: str) -> None:
    if not _ALLOWED.match(text or ""):
        raise ValueError("Citation contract violated")
