from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QInputDialog, QLineEdit, QWidget

from .models import ImageEntry


@dataclass(frozen=True)
class ArchiveAccessDecision:
    allowed: bool
    password: bytes | None = None
    error_message: str | None = None


class ArchiveAccess:
    """Keep traditional ZIP passwords in memory for the current app session."""

    def __init__(self) -> None:
        self._passwords: dict[Path, bytes] = {}

    def request(
        self,
        entry: ImageEntry,
        parent: QWidget,
    ) -> ArchiveAccessDecision:
        if entry.encryption is None:
            return ArchiveAccessDecision(True)
        if entry.encryption == "aes":
            return ArchiveAccessDecision(
                False,
                error_message="AES 방식으로 암호화된 ZIP은 지원하지 않습니다.",
            )

        cached = self.cached_password(entry)
        if cached is not None:
            return ArchiveAccessDecision(True, cached)
        password, accepted = QInputDialog.getText(
            parent,
            "ZIP 암호",
            f"{entry.archive_label}의 암호를 입력하세요.",
            QLineEdit.EchoMode.Password,
        )
        if not accepted:
            return ArchiveAccessDecision(
                False,
                error_message="ZIP 암호 입력을 취소했습니다.",
            )

        encoded_password = password.encode("utf-8")
        self._passwords[entry.archive_path] = encoded_password
        return ArchiveAccessDecision(True, encoded_password)

    def cached_password(self, entry: ImageEntry) -> bytes | None:
        if entry.encryption != "zipcrypto":
            return None
        return self._passwords.get(entry.archive_path)

    def invalidate_password(self, entry: ImageEntry) -> None:
        self._passwords.pop(entry.archive_path, None)

