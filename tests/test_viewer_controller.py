from __future__ import annotations

from pathlib import Path

from zippictureviewer.folder_context import FolderContext
from zippictureviewer.models import ImageEntry
from zippictureviewer.viewer_controller import ViewerController


def test_new_source_is_applied_only_after_matching_scan_finishes(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    controller = ViewerController()

    first_generation = controller.begin_load(FolderContext.from_path(first))
    second_generation = controller.begin_load(FolderContext.from_path(second))

    assert not controller.apply_load(
        first_generation,
        [ImageEntry(first, "stale.png")],
    )
    assert controller.current_context is None

    assert controller.apply_load(
        second_generation,
        [ImageEntry(second, "current.png")],
    )
    assert controller.current_context == FolderContext.from_path(second)
    assert controller.state.current_entry == ImageEntry(second, "current.png")


def test_failed_pending_load_preserves_current_source(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    controller = ViewerController()
    first_context = FolderContext.from_path(first)
    first_generation = controller.begin_load(first_context)
    controller.apply_load(first_generation, [ImageEntry(first, "page.png")])

    failed_generation = controller.begin_load(FolderContext.from_path(second))
    assert controller.reject_load(failed_generation)

    assert controller.current_context == first_context
    assert controller.state.current_entry == ImageEntry(first, "page.png")


def test_display_tokens_reject_results_after_navigation(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    entries = [ImageEntry(root, "1.png"), ImageEntry(root, "2.png")]
    controller = ViewerController()
    generation = controller.begin_load(FolderContext.from_path(root))
    controller.apply_load(generation, entries)

    first_token = controller.begin_display()
    assert first_token is not None
    assert controller.state.move_next()
    second_token = controller.begin_display()

    assert second_token is not None
    assert not controller.is_current_display(first_token)
    assert controller.is_current_display(second_token)
