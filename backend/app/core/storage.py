from __future__ import annotations

import os
import pathlib
import secrets
from dataclasses import dataclass
from typing import BinaryIO, Tuple

@dataclass(frozen=True)
class StoredFile:
    storage_key: str         # 例: "pdfs/<doc_id>/<random>.pdf"
    abs_path: str            # 例: "/var/data/ragqa/pdfs/<doc_id>/<random>.pdf"
    size_bytes: int

class FileStorage:
    """
    Render Disk の mount path 配下に書き込む。
    mount path 以外はデプロイ/再起動で消えるので注意。
    """
    def __init__(self, base_dir: str, pdf_subdir: str = "pdfs") -> None:
        self.base_dir = os.path.abspath(base_dir)
        self.pdf_root = os.path.join(self.base_dir, pdf_subdir)

    def ensure_dirs(self) -> None:
        os.makedirs(self.pdf_root, exist_ok=True)

    def save_pdf_stream(
        self,
        doc_id: str,
        src: BinaryIO,
        original_filename: str,
        max_bytes: int
    ) -> StoredFile:
        self.ensure_dirs()

        safe_name = (pathlib.Path(original_filename).name or "upload.pdf").replace("\x00", "")
        ext = pathlib.Path(safe_name).suffix.lower()
        if ext != ".pdf":
            # ここは要件次第。PDF限定なら弾く方が安全
            raise ValueError("Only .pdf is allowed")

        # doc別ディレクトリ
        doc_dir = os.path.join(self.pdf_root, doc_id)
        os.makedirs(doc_dir, exist_ok=True)

        rand = secrets.token_urlsafe(16)
        storage_key = f"pdfs/{doc_id}/{rand}.pdf"
        abs_path = os.path.join(doc_dir, f"{rand}.pdf")

        # 原子的に書く（途中失敗で壊れたファイルを残しにくい）
        tmp_path = abs_path + ".tmp"

        size = 0
        with open(tmp_path, "wb") as f:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    try:
                        f.close()
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    raise ValueError(f"File too large (>{max_bytes} bytes)")
                f.write(chunk)

        os.replace(tmp_path, abs_path)
        return StoredFile(storage_key=storage_key, abs_path=abs_path, size_bytes=size)

    def open_for_read(self, abs_path: str) -> Tuple[BinaryIO, int]:
        st = os.stat(abs_path)
        return open(abs_path, "rb"), st.st_size
