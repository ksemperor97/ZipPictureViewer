from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QColor, QImage

from zippictureviewer.session_store import SessionStore
from zippictureviewer.models import ScanIssue
from zippictureviewer.viewer_window import MainWindow


def _window(qtbot, monkeypatch, tmp_path: Path) -> MainWindow:
    monkeypatch.setattr(MainWindow, "_restore_last_source", lambda self: None)
    window = MainWindow()
    window.session_store = SessionStore(tmp_path / "session.json")
    qtbot.addWidget(window)
    window.show()
    return window


def _write_png(path: Path, color: str = "blue") -> bytes:
    image = QImage(24, 16, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")
    return path.read_bytes()


def test_corrupt_image_and_bad_zip_do_not_block_navigation(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "1-broken.png").write_bytes(b"not a png")
    _write_png(tmp_path / "2-good.png")
    (tmp_path / "bad.zip").write_bytes(b"not a zip")
    window = _window(qtbot, monkeypatch, tmp_path)

    window.load_source(tmp_path)
    qtbot.waitUntil(lambda: len(window.presenter.errors) == 1, timeout=3000)

    assert len(window.state.entries) == 2
    assert len(window.controller.scan_issues) == 1
    assert window.state.current_entry.member_name == "1-broken.png"
    assert window.image_view.current_pixmap.isNull()
    assert window.file_label.full_text.endswith("1-broken.png")
    assert window.next_button.isEnabled()
    assert window.issues_button.text() == "오류 2"

    window.next_button.click()
    qtbot.waitUntil(
        lambda: not window.image_view.current_pixmap.isNull(),
        timeout=3000,
    )
    assert window.state.current_entry.member_name == "2-good.png"
    assert window.status_label.text() == "2 / 2"


def test_direct_archive_and_drop_use_the_same_source_path(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    png_bytes = _write_png(tmp_path / "source.png", "green")
    archive_path = tmp_path / "book.cbz"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("page.png", png_bytes)
    (tmp_path / "source.png").unlink()
    window = _window(qtbot, monkeypatch, tmp_path)

    mime_data = QMimeData()
    mime_data.setUrls([QUrl.fromLocalFile(str(archive_path))])
    assert window._dropped_source(mime_data) == archive_path

    window.load_source(archive_path)
    qtbot.waitUntil(
        lambda: not window.image_view.current_pixmap.isNull(),
        timeout=3000,
    )
    assert window.current_context.source_kind == "archive"
    assert window.current_root == archive_path
    assert window.state.current_entry.member_name == "page.png"


def test_empty_and_unsupported_folders_have_distinct_messages(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    window = _window(qtbot, monkeypatch, tmp_path)
    window.load_source(tmp_path)
    qtbot.waitUntil(
        lambda: window.image_view.current_message == "빈 폴더입니다",
        timeout=3000,
    )

    (tmp_path / "notes.txt").write_text("unsupported", encoding="utf-8")
    previous_generation = window.controller.load_generation
    window.refresh_source()
    qtbot.waitUntil(
        lambda: window.controller.load_generation > previous_generation
        and window.image_view.current_message
        == "지원되는 이미지 형식이 없습니다",
        timeout=3000,
    )


def test_issue_dialog_shows_every_error_without_blocking(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    window = _window(qtbot, monkeypatch, tmp_path)
    window.controller.scan_issues = [
        ScanIssue(
            target_path=tmp_path / f"broken-{index}.zip",
            stage="scan_archive",
            error_kind="bad_zip",
            message=f"failure {index}",
        )
        for index in range(35)
    ]
    window._update_issues_button()

    window.show_issues()

    assert window.issue_dialog.isVisible()
    assert not window.issue_dialog.isModal()
    assert "failure 0" in window.issue_dialog.details.toPlainText()
    assert "failure 34" in window.issue_dialog.details.toPlainText()
    assert window.issue_dialog.summary_label.text().startswith("오류 35개")
    window.close()


def test_shortcut_help_is_available_inside_the_app(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    window = _window(qtbot, monkeypatch, tmp_path)
    window._set_overlays_visible(True)

    window.help_button.click()

    assert window.shortcut_help_dialog.isVisible()
    assert not window.shortcut_help_dialog.isModal()
    window.close()
