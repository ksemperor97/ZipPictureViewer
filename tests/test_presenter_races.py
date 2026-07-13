from __future__ import annotations

import base64
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QInputDialog, QWidget

from zippictureviewer.archive_access import ArchiveAccessDecision
from zippictureviewer.archive_scanner import scan_image_index
from zippictureviewer.decode_worker import DecodedPayload
from zippictureviewer.folder_context import FolderContext
from zippictureviewer.image_view import ImageView
from zippictureviewer.models import ContainerRevision, ImageEntry
from zippictureviewer.viewer_controller import ViewerController
from zippictureviewer.viewer_presenter import ImagePresenter


def _solid_image(color: str, width: int = 100, height: int = 80) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    return image


def _write_png(path: Path, color: str = "blue") -> tuple[ImageEntry, QImage]:
    image = _solid_image(color)
    assert image.save(str(path), "PNG")
    return (
        ImageEntry(
            path.parent,
            path.name,
            source_revision=ContainerRevision.from_path(path),
            source_kind="folder",
        ),
        image,
    )


def _make_presenter(
    qtbot,
    context: FolderContext,
    entries: list[ImageEntry],
) -> tuple[ImagePresenter, ViewerController, ImageView]:
    parent = QWidget()
    parent.resize(640, 480)
    image_view = ImageView()
    image_view.setParent(parent)
    image_view.setGeometry(parent.rect())
    qtbot.addWidget(parent)
    parent.show()

    controller = ViewerController()
    generation = controller.begin_load(context)
    assert controller.apply_load(generation, entries)
    presenter = ImagePresenter(controller, image_view, parent)
    return presenter, controller, image_view


def test_fit_during_initial_preview_keeps_the_preview_request_current(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    entry, image = _write_png(tmp_path / "page.png")
    presenter, controller, image_view = _make_presenter(
        qtbot,
        FolderContext.from_path(tmp_path),
        [entry],
    )
    requests: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(
        presenter.decoder,
        "request",
        lambda token, **options: requests.append((token, options)),
    )

    presenter.show_current()
    preview_token = requests[0][0]
    image_view.request_fit()

    assert controller.is_current_display(preview_token)
    assert len(requests) == 1
    presenter._decoded(
        preview_token,
        DecodedPayload(image=image, source_revision=entry.source_revision),
        False,
    )
    assert not image_view.current_pixmap.isNull()
    assert image_view.current_message == ""


@pytest.mark.parametrize("zoom_method", ("zoom_in", "zoom_out"))
def test_zoom_invalidates_a_pending_resize_fit_upgrade(
    qtbot,
    monkeypatch,
    tmp_path: Path,
    zoom_method: str,
) -> None:
    entry, _image = _write_png(tmp_path / "page.png")
    presenter, controller, image_view = _make_presenter(
        qtbot,
        FolderContext.from_path(tmp_path),
        [entry],
    )
    initial_token = controller.begin_display()
    assert initial_token is not None
    presenter._show_decoded_image(initial_token, _solid_image("blue"))
    requests: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(
        presenter.decoder,
        "request",
        lambda token, **options: requests.append((token, options)),
    )

    presenter._refresh_fit_preview()
    fit_upgrade_token = requests[0][0]
    assert controller.is_current_display(fit_upgrade_token)

    getattr(image_view, zoom_method)()
    assert not controller.is_current_display(fit_upgrade_token)
    presenter._decoded(
        fit_upgrade_token,
        DecodedPayload(
            image=_solid_image("red", 640, 480),
            source_revision=entry.source_revision,
        ),
        False,
    )

    assert not image_view.fit_mode
    assert image_view.current_pixmap.toImage().pixelColor(0, 0) == QColor("blue")
    presenter._zoom_timer.stop()


@pytest.mark.parametrize(
    "decision",
    [
        ArchiveAccessDecision(
            False,
            error_message="ZIP 암호 입력을 취소했습니다.",
        ),
        ArchiveAccessDecision(True, password=b"secret"),
    ],
    ids=("cancelled", "accepted"),
)
def test_reentrant_password_prompt_cannot_overwrite_a_new_source(
    qtbot,
    monkeypatch,
    tmp_path: Path,
    decision: ArchiveAccessDecision,
) -> None:
    old_archive = tmp_path / "old.zip"
    old_archive.touch()
    old_entry = ImageEntry(
        old_archive,
        "old.png",
        source_kind="archive",
        encryption="zipcrypto",
    )
    presenter, controller, image_view = _make_presenter(
        qtbot,
        FolderContext.from_path(old_archive),
        [old_entry],
    )
    new_root = tmp_path / "new"
    new_root.mkdir()
    new_entry = ImageEntry(new_root, "new.png", source_kind="folder")
    decode_requests: list[object] = []
    monkeypatch.setattr(
        presenter.decoder,
        "request",
        lambda token, **_options: decode_requests.append(token),
    )

    def reentrant_access(*_args) -> ArchiveAccessDecision:
        generation = controller.begin_load(FolderContext.from_path(new_root))
        assert controller.apply_load(generation, [new_entry])
        new_token = controller.begin_display()
        assert new_token is not None
        presenter.current_pixmap = QPixmap.fromImage(_solid_image("green"))
        image_view.set_pixmap(presenter.current_pixmap)
        return decision

    monkeypatch.setattr(presenter.archive_access, "request", reentrant_access)

    presenter.show_current()

    assert controller.state.current_entry == new_entry
    assert presenter.current_pixmap is not None
    assert presenter.current_pixmap.toImage().pixelColor(0, 0) == QColor("green")
    assert presenter.errors == {}
    assert decode_requests == []


def test_show_current_is_a_noop_after_shutdown(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    entry, _image = _write_png(tmp_path / "page.png")
    presenter, controller, _image_view = _make_presenter(
        qtbot,
        FolderContext.from_path(tmp_path),
        [entry],
    )
    access_calls: list[ImageEntry] = []
    decode_requests: list[object] = []
    monkeypatch.setattr(
        presenter.archive_access,
        "request",
        lambda requested_entry, _parent: (
            access_calls.append(requested_entry) or ArchiveAccessDecision(True)
        ),
    )
    monkeypatch.setattr(
        presenter.decoder,
        "request",
        lambda token, **_options: decode_requests.append(token),
    )

    presenter.begin_shutdown()
    shutdown_generation = controller.display_generation
    presenter.show_current()

    assert controller.display_generation == shutdown_generation
    assert access_calls == []
    assert decode_requests == []


@pytest.mark.parametrize(
    ("password", "password_remains_cached"),
    (("secret", True), ("wrong", False)),
)
def test_only_an_invalid_password_clears_the_cached_zip_password(
    qtbot,
    monkeypatch,
    tmp_path: Path,
    password: str,
    password_remains_cached: bool,
) -> None:
    encrypted_zip = base64.b64decode(
        "UEsDBAoACQAAAFi97Vxyo8w1LAAAACAAAAAIABwAcGFnZS5wbmdVVAkAA2j5VGpo"
        "+VRqdXgLAAEE9QEAAAQUAAAAABDOj3sL8fFd4NdnJ8TqY2jWOhoO7hym8kaNAT1g"
        "ZH3qsrs+IfdQl2V77UlQSwcIcqPMNSwAAAAgAAAAUEsBAh4DCgAJAAAAWL3tXHKj"
        "zDUsAAAAIAAAAAgAGAAAAAAAAQAAAKSBAAAAAHBhZ2UucG5nVVQFAANo+VRqdXgL"
        "AAEE9QEAAAQUAAAAUEsFBgAAAAABAAEATgAAAH4AAAAAAA=="
    )
    archive_path = tmp_path / "encrypted.zip"
    archive_path.write_bytes(encrypted_zip)
    entry = scan_image_index(archive_path).entries[0]
    presenter, _controller, _image_view = _make_presenter(
        qtbot,
        FolderContext.from_path(archive_path),
        [entry],
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: (password, True),
    )

    presenter.show_current()
    qtbot.waitUntil(lambda: entry in presenter.errors, timeout=3000)

    cached_password = presenter.archive_access.cached_password(entry)
    if password_remains_cached:
        assert cached_password == b"secret"
        assert "재입력" not in presenter.errors[entry]
    else:
        assert cached_password is None
        assert "재입력" in presenter.errors[entry]


def test_full_resolution_prompts_for_password_and_cancels_pending_zoom(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "encrypted.zip"
    archive_path.touch()
    entry = ImageEntry(
        archive_path,
        "page.png",
        source_kind="archive",
        encryption="zipcrypto",
    )
    presenter, controller, image_view = _make_presenter(
        qtbot,
        FolderContext.from_path(archive_path),
        [entry],
    )
    initial_token = controller.begin_display()
    assert initial_token is not None
    presenter._show_decoded_image(initial_token, _solid_image("blue", 320, 200))
    prompt_count = 0

    def enter_password(*_args, **_kwargs):
        nonlocal prompt_count
        prompt_count += 1
        return "secret", True

    monkeypatch.setattr(QInputDialog, "getText", enter_password)
    requests: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(
        presenter.decoder,
        "request",
        lambda token, **options: requests.append((token, options)),
    )

    image_view.zoom_in()
    assert presenter._zoom_timer.isActive()
    image_view.actual_size()
    qtbot.wait(200)

    assert prompt_count == 1
    assert len(requests) == 1
    request_token, options = requests[0]
    assert controller.is_current_display(request_token)
    assert options["password"] == b"secret"
    assert options.get("scaled_size") is None
    assert not presenter._zoom_timer.isActive()
