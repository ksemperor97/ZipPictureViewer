from __future__ import annotations

from pathlib import Path

from zippictureviewer.folder_context import FolderContext
from zippictureviewer.models import ImageEntry, ScanResult
from zippictureviewer.session_store import SessionStore
from zippictureviewer.source_loader import SourceLoader
from zippictureviewer.viewer_controller import ViewerController


def test_inaccessible_latest_request_supersedes_the_pending_scan(
    qapp,
    monkeypatch,
    tmp_path: Path,
) -> None:
    current_root = tmp_path / "current"
    pending_root = tmp_path / "pending"
    missing_root = tmp_path / "missing"
    current_root.mkdir()
    pending_root.mkdir()

    controller = ViewerController()
    current_context = FolderContext.from_path(current_root)
    current_entry = ImageEntry(current_root, "current.png", source_kind="folder")
    current_generation = controller.begin_load(current_context)
    assert controller.apply_load(current_generation, [current_entry])

    loader = SourceLoader(
        controller,
        SessionStore(tmp_path / "session.json"),
    )
    started_generations: list[int] = []
    cancelled_except: list[int] = []
    scanning_states: list[bool] = []
    applied_sources: list[FolderContext] = []
    rejected_messages: list[str] = []
    monkeypatch.setattr(
        loader.scanner,
        "start",
        lambda _root, generation, _options: started_generations.append(generation),
    )
    monkeypatch.setattr(
        loader.scanner,
        "cancel_except",
        lambda generation: cancelled_except.append(generation),
    )
    loader.scanning_changed.connect(scanning_states.append)
    loader.source_applied.connect(
        lambda context, _result: applied_sources.append(context)
    )
    loader.source_rejected.connect(rejected_messages.append)

    assert loader.load(pending_root)
    pending_generation = controller.load_generation

    assert not loader.load(missing_root)
    latest_generation = controller.load_generation
    assert latest_generation > pending_generation
    assert cancelled_except == [latest_generation]
    assert controller.pending_context is None
    assert controller.current_context == current_context
    assert controller.state.current_entry == current_entry
    assert scanning_states == [True, False]
    assert rejected_messages == [f"열 수 없는 경로: {missing_root}"]

    stale_entry = ImageEntry(pending_root, "stale.png", source_kind="folder")
    loader._scan_finished(
        pending_generation,
        ScanResult(entries=[stale_entry], generation=pending_generation),
    )

    assert started_generations == [pending_generation]
    assert applied_sources == []
    assert controller.current_context == current_context
    assert controller.state.current_entry == current_entry
