from __future__ import annotations

import json
from pathlib import Path

from zippictureviewer.folder_context import FolderContext
from zippictureviewer.models import ImageEntry
from zippictureviewer.position_saver import PositionSaver
from zippictureviewer.session_store import SessionStore
from zippictureviewer.viewer_state import ViewerState


def test_position_writes_are_debounced_and_keep_latest_entry(
    qtbot,
    tmp_path: Path,
) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    archive = root / "book.zip"
    archive.touch()
    entries = [
        ImageEntry(archive, f"page-{index}.png", source_kind="archive")
        for index in range(3)
    ]
    state = ViewerState(entries)
    store = SessionStore(tmp_path / "session.json")
    saver = PositionSaver(store, delay_ms=1000)
    context = FolderContext.from_path(root)

    saver.schedule(context, state)
    state.current_index = 2
    saver.schedule(context, state)

    assert saver.timer.isActive()
    assert not store.path.exists()
    saver.flush()

    saved = json.loads(store.path.read_text(encoding="utf-8"))
    position = saved["positions"][context.session_key]
    assert position["member_id"] == "page-2.png"
    assert position["container_index"] == 2
    assert store.restore_index(context, entries) == 2
