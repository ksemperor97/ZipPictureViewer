from __future__ import annotations

from threading import Event
from time import monotonic

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QWidget

from zippictureviewer.decode_worker import DecodedPayload
from zippictureviewer.folder_context import FolderContext
from zippictureviewer.image_view import ImageView
from zippictureviewer.models import ImageEntry, ScanResult
from zippictureviewer.session_store import SessionStore
from zippictureviewer.source_loader import SourceLoader
from zippictureviewer.viewer_controller import DisplayToken, ViewerController
from zippictureviewer.viewer_presenter import ImagePresenter
from zippictureviewer.viewer_window import MainWindow


def _make_window(qtbot, monkeypatch) -> MainWindow:
    monkeypatch.setattr(MainWindow, "_restore_last_source", lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    return window


def _solid_image(color: str, width: int = 32, height: int = 24) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    return image


def _make_presenter(qtbot, tmp_path):
    parent = QWidget()
    image_view = ImageView()
    image_view.setParent(parent)
    parent.resize(640, 480)
    qtbot.addWidget(parent)
    parent.show()

    controller = ViewerController()
    context = FolderContext.from_path(tmp_path)
    entries = [
        ImageEntry(tmp_path, "first.png", source_kind="folder"),
        ImageEntry(tmp_path, "second.png", source_kind="folder"),
    ]
    generation = controller.begin_load(context)
    assert controller.apply_load(generation, entries)
    presenter = ImagePresenter(controller, image_view, parent)
    return presenter, controller, image_view, entries


def test_close_waits_for_a_running_scan_thread(qtbot, monkeypatch, tmp_path) -> None:
    import zippictureviewer.scan_worker as scan_worker

    started = Event()
    release = Event()

    def slow_scan(
        root,
        *,
        options=None,
        generation=0,
        cancel_check=None,
        progress_callback=None,
    ) -> ScanResult:
        started.set()
        release.wait(5.0)
        return ScanResult(
            cancelled=bool(cancel_check and cancel_check()),
            generation=generation,
        )

    monkeypatch.setattr(scan_worker, "scan_image_index", slow_scan)
    window = _make_window(qtbot, monkeypatch)
    window.load_source(tmp_path)
    qtbot.waitUntil(started.is_set, timeout=2000)
    job = next(iter(window.scanner._jobs.values()))

    try:
        close_started = monotonic()
        closed = window.close()
        close_elapsed = monotonic() - close_started

        assert not closed
        assert close_elapsed < 1.0
        assert window.isVisible()
        assert window.scanner.active_count == 1
        assert job.thread.isRunning()
    finally:
        release.set()

    qtbot.waitUntil(lambda: window.scanner.active_count == 0, timeout=3000)
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=3000)


def test_immediate_close_cancels_deferred_session_restore(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    root = tmp_path / "last-source"
    root.mkdir()
    store = SessionStore(tmp_path / "session.json")
    store.save_root(root)
    load_calls = []
    monkeypatch.setattr(
        "zippictureviewer.viewer_window.SessionStore",
        lambda: store,
    )
    monkeypatch.setattr(
        SourceLoader,
        "load",
        lambda _self, context: load_calls.append(context) or True,
    )

    window = MainWindow()
    qtbot.addWidget(window)
    assert window._restore_timer.isActive()

    assert window.close()
    qtbot.wait(10)

    assert not window._restore_timer.isActive()
    assert load_calls == []


def test_stale_foreground_and_preload_results_are_discarded(
    qtbot,
    tmp_path,
) -> None:
    presenter, controller, image_view, entries = _make_presenter(qtbot, tmp_path)
    baseline = _solid_image("blue")
    presenter.current_pixmap = QPixmap.fromImage(baseline)
    image_view.set_pixmap(presenter.current_pixmap)

    stale_foreground = controller.begin_display()
    assert stale_foreground is not None
    assert controller.state.move_next()
    current = controller.begin_display()
    assert current is not None

    stale_preload = DisplayToken(stale_foreground.generation, entries[1])
    presenter._preload_pending.add(entries[1])
    presenter._decoded(
        stale_preload,
        DecodedPayload(image=_solid_image("green")),
        True,
    )
    presenter._decoded(
        stale_foreground,
        DecodedPayload(image=_solid_image("red")),
        False,
    )

    assert presenter.cache.item_count == 0
    assert image_view.current_pixmap.toImage().pixelColor(0, 0) == QColor("blue")
    assert controller.is_current_display(current)


def test_narrow_window_keeps_controls_and_file_info_usable(
    qtbot,
    monkeypatch,
) -> None:
    window = _make_window(qtbot, monkeypatch)
    long_path = "/collection/" + "/very-long-folder-name" * 30 + "/page.png"
    window.resize(480, 360)
    window.file_label.setText(long_path)
    window._set_overlays_visible(True)
    window.viewer_surface.position_floating_panels()
    qtbot.waitUntil(window.info_panel.isVisible)

    controls = window.controls_panel.geometry()
    info = window.info_panel.geometry()
    grip = window.viewer_surface.resize_grip.geometry()
    surface = window.viewer_surface.rect()

    assert surface.contains(controls)
    assert surface.contains(info)
    assert not info.intersects(grip)
    assert min(button.width() for button in window.controls_panel.buttons()) >= 52
    assert window.file_label.full_text == long_path
    assert window.file_label.text() != long_path
    assert "…" in window.file_label.text()
    assert window.file_label.toolTip() == long_path
    assert window.file_label.textInteractionFlags() & (
        Qt.TextInteractionFlag.TextSelectableByMouse
    )

    window.close()


def test_combo_up_key_is_not_taken_by_archive_navigation_shortcut(
    qtbot,
    monkeypatch,
) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._set_overlays_visible(True)
    window.encoding_combo.setCurrentIndex(1)

    # QTest targets the combo directly while still allowing ancestor shortcuts
    # to participate in normal shortcut dispatch.
    qtbot.keyClick(window.encoding_combo, Qt.Key.Key_Up)

    assert window.encoding_combo.currentIndex() == 0
    window.close()


def test_native_fullscreen_exit_resynchronizes_button_and_resize_grip(
    qtbot,
    monkeypatch,
) -> None:
    window = _make_window(qtbot, monkeypatch)
    window._set_overlays_visible(True)
    assert window.viewer_surface.resize_grip.isVisible()

    window.showFullScreen()
    qtbot.waitUntil(
        lambda: window.isFullScreen()
        and window.fullscreen_button.text() == "창모드",
        timeout=2000,
    )
    assert not window.viewer_surface.resize_grip.isVisible()

    # Exercise an OS/native state transition, not MainWindow.exit_fullscreen().
    window.showNormal()
    qtbot.waitUntil(
        lambda: not window.isFullScreen()
        and window.fullscreen_button.text() == "전체화면"
        and window.viewer_surface.resize_grip.isVisible(),
        timeout=2000,
    )

    window.close()


def test_deleted_pending_root_preserves_the_current_context(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    window = _make_window(qtbot, monkeypatch)
    current_root = tmp_path / "current"
    pending_root = tmp_path / "pending"
    current_root.mkdir()
    pending_root.mkdir()
    current_context = FolderContext.from_path(current_root)
    pending_context = FolderContext.from_path(pending_root)
    current_entry = ImageEntry(
        current_root,
        "page.png",
        source_kind="folder",
    )

    first_generation = window.controller.begin_load(current_context)
    assert window.controller.apply_load(first_generation, [current_entry])
    window.current_root = current_context.logical_path
    pending_generation = window.controller.begin_load(pending_context)
    pending_root.rmdir()

    window.source_loader._scan_finished(
        pending_generation,
        ScanResult(generation=pending_generation),
    )

    assert window.current_context == current_context
    assert window.current_root == current_context.logical_path
    assert window.state.current_entry == current_entry
    assert window.controller.pending_context is None
    window.close()


def test_full_resolution_failure_preserves_the_fitted_preview(
    qtbot,
    tmp_path,
) -> None:
    presenter, controller, image_view, _entries = _make_presenter(qtbot, tmp_path)
    preview = _solid_image("purple", 320, 200)
    preview_token = controller.begin_display()
    assert preview_token is not None
    presenter._show_decoded_image(preview_token, preview)
    assert presenter.current_pixmap is not None
    preview_cache_key = presenter.current_pixmap.cacheKey()

    full_resolution_token = controller.begin_display()
    assert full_resolution_token is not None
    presenter._decode_failed(
        full_resolution_token,
        "decoded image exceeds the memory limit",
        False,
        True,
    )

    assert presenter.current_pixmap is not None
    assert presenter.current_pixmap.cacheKey() == preview_cache_key
    assert image_view.current_pixmap.cacheKey() == preview_cache_key
    assert image_view.fit_mode


def test_late_full_resolution_result_cannot_override_newer_fit_request(
    qtbot,
    tmp_path,
) -> None:
    presenter, controller, image_view, _entries = _make_presenter(qtbot, tmp_path)
    preview_token = controller.begin_display()
    assert preview_token is not None
    presenter._show_decoded_image(preview_token, _solid_image("blue"))

    full_resolution_token = controller.begin_display()
    assert full_resolution_token is not None
    image_view._fit_mode = False
    image_view.request_fit()
    assert image_view.fit_mode

    presenter._decoded(
        full_resolution_token,
        DecodedPayload(
            image=_solid_image("red", 128, 96),
            full_resolution=True,
        ),
        False,
    )

    assert image_view.fit_mode
    assert image_view.current_pixmap.toImage().pixelColor(0, 0) == QColor("blue")


def test_zoom_requests_more_pixels_without_changing_visual_zoom(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    presenter, controller, image_view, _entries = _make_presenter(qtbot, tmp_path)
    token = controller.begin_display()
    assert token is not None
    presenter._show_decoded_image(token, _solid_image("blue", 320, 200))
    requests = []
    monkeypatch.setattr(
        presenter.decoder,
        "request",
        lambda request_token, **options: requests.append(
            (request_token, options)
        ),
    )

    image_view.zoom_in()
    zoom_before_upgrade = image_view.transform().m11()
    qtbot.waitUntil(lambda: bool(requests), timeout=1000)
    request_token, options = requests[-1]

    assert options["preserve_zoom"]
    assert options["scaled_size"].width() == 640
    presenter._show_decoded_image(
        request_token,
        _solid_image("blue", 640, 400),
        preserve_zoom=True,
    )
    assert not image_view.fit_mode
    assert image_view.transform().m11() < zoom_before_upgrade
    assert image_view.current_pixmap.size().toTuple() == (640, 400)


def test_successful_retry_clears_the_previous_error(qtbot, tmp_path) -> None:
    presenter, controller, _image_view, entries = _make_presenter(qtbot, tmp_path)
    failed_token = controller.begin_display()
    assert failed_token is not None
    presenter._show_decode_error(failed_token, "temporary failure")
    assert entries[0] in presenter.errors

    retry_token = controller.begin_display()
    assert retry_token is not None
    presenter._show_decoded_image(retry_token, _solid_image("green"))

    assert entries[0] not in presenter.errors


def test_fit_cancels_a_debounced_zoom_resolution_request(
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    presenter, controller, image_view, _entries = _make_presenter(qtbot, tmp_path)
    token = controller.begin_display()
    assert token is not None
    presenter._show_decoded_image(token, _solid_image("blue", 320, 200))
    requests = []
    monkeypatch.setattr(
        presenter.decoder,
        "request",
        lambda *args, **kwargs: requests.append((args, kwargs)),
    )

    image_view.zoom_in()
    image_view.request_fit()
    qtbot.wait(200)

    assert image_view.fit_mode
    assert requests == []
