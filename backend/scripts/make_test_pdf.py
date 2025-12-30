#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def _escape_pdf_string(s: str) -> str:
    # Escape backslash and parentheses for PDF literal strings.
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_minimal_pdf(lines: list[str]) -> bytes:
    """
    Build a minimal, text-extractable, single-page PDF without external deps.

    Structure:
      1 0 obj: Catalog
      2 0 obj: Pages
      3 0 obj: Page
      4 0 obj: Helvetica font
      5 0 obj: Contents stream (BT..ET)
    """
    # Content stream (simple text lines)
    # Use PDF text operators: BT /F1 12 Tf x y Td (...) Tj ... ET
    # Place lines downward using Td.
    x, y = 72, 720
    leading = 18

    ops: list[str] = []
    ops.append("BT")
    ops.append("/F1 12 Tf")
    ops.append(f"{x} {y} Td")
    for i, line in enumerate(lines):
        lit = _escape_pdf_string(line)
        ops.append(f"({lit}) Tj")
        if i != len(lines) - 1:
            ops.append(f"0 -{leading} Td")
    ops.append("ET")
    stream_data = ("\n".join(ops) + "\n").encode("ascii")

    obj1 = b"<< /Type /Catalog /Pages 2 0 R >>"
    obj2 = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    obj3 = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    obj4 = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    obj5 = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream_data), stream_data)

    objects = [obj1, obj2, obj3, obj4, obj5]

    # Write file and compute xref offsets
    out = bytearray()
    out += b"%PDF-1.4\n"
    out += b"%\xe2\xe3\xcf\xd3\n"  # binary comment line

    offsets: list[int] = [0]  # object 0 placeholder

    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii")
        out += body
        if not out.endswith(b"\n"):
            out += b"\n"
        out += b"endobj\n"

    xref_pos = len(out)
    out += b"xref\n"
    out += f"0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("ascii")

    out += b"trailer\n"
    out += f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii")
    out += b"startxref\n"
    out += f"{xref_pos}\n".encode("ascii")
    out += b"%%EOF\n"

    return bytes(out)


def main() -> int:
    out_path = sys.argv[1] if len(sys.argv) >= 2 else "ragqa_ci_test.pdf"

    lines = [
        "RAG QA CI Test Document",
        "Stakeholders: Alice, Bob",
        "Evidence: EVIDENCE-001, EVIDENCE-002",
        "Key phrase: ALICE_BOB_EVIDENCE",
    ]

    data = build_minimal_pdf(lines)
    pathlib.Path(out_path).write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
