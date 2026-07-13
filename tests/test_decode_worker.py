from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from zippictureviewer.decode_worker import AsyncDecoder
from zippictureviewer.image_loader import ResourceLimitError
from zippictureviewer.models import ImageEntry
from zippictureviewer.viewer_controller import DisplayToken


def test_async_decoder_loads_a_still_image(tmp_path: Path, qtbot) -> None:
    image_path = tmp_path / "page.png"
    image = QImage(4, 3, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(image_path), "PNG")
    token = DisplayToken(1, ImageEntry(tmp_path, image_path.name))
    decoder = AsyncDecoder()

    with qtbot.waitSignal(decoder.ready, timeout=3000) as signal:
        decoder.request(token)

    returned_token, payload, preload = signal.args
    assert returned_token == token
    assert payload.image is not None
    assert payload.image.size() == image.size()
    assert payload.animation_bytes is None
    assert not preload


def test_async_decoder_reports_failure_without_raising(tmp_path: Path, qtbot) -> None:
    missing = ImageEntry(tmp_path, "missing.png")
    token = DisplayToken(2, missing)
    decoder = AsyncDecoder()

    with qtbot.waitSignal(decoder.failed, timeout=3000) as signal:
        decoder.request(token)

    (
        returned_token,
        message,
        preload,
        full_resolution,
        preserve_zoom,
        invalid_password,
        resource_limit,
    ) = signal.args
    assert returned_token == token
    assert "missing.png" in message or "No such file" in message
    assert not preload
    assert full_resolution
    assert not preserve_zoom
    assert not invalid_password
    assert not resource_limit


def test_async_decoder_separates_fit_preview_from_full_resolution(
    tmp_path: Path,
    qtbot,
) -> None:
    image_path = tmp_path / "large.png"
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("blue"))
    assert image.save(str(image_path), "PNG")
    token = DisplayToken(3, ImageEntry(tmp_path, image_path.name))
    decoder = AsyncDecoder()

    with qtbot.waitSignal(decoder.ready, timeout=3000) as preview_signal:
        decoder.request(token, scaled_size=QSize(100, 100))
    preview_payload = preview_signal.args[1]
    assert preview_payload.image.size().toTuple() == (100, 80)
    assert not preview_payload.full_resolution

    with qtbot.waitSignal(decoder.ready, timeout=3000) as full_signal:
        decoder.request(token)
    full_payload = full_signal.args[1]
    assert full_payload.image.size() == image.size()
    assert full_payload.full_resolution


def test_async_decoder_classifies_resource_limit_failures(
    tmp_path: Path,
    qtbot,
    monkeypatch,
) -> None:
    import zippictureviewer.decode_worker as decode_worker

    (tmp_path / "large.png").write_bytes(b"placeholder")
    entry = ImageEntry(tmp_path, "large.png", source_kind="folder")
    token = DisplayToken(4, entry)
    decoder = AsyncDecoder()
    monkeypatch.setattr(
        decode_worker,
        "load_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(ResourceLimitError("too large")),
    )

    with qtbot.waitSignal(decoder.failed, timeout=3000) as signal:
        decoder.request(token, scaled_size=QSize(100, 100))

    assert signal.args[-1] is True
