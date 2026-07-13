from pathlib import Path

from zippictureviewer.models import ImageEntry
from zippictureviewer.viewer_state import ViewerState


def _entry(container: str, member: str) -> ImageEntry:
    return ImageEntry(Path(container), member, source_kind="archive")


def test_single_container_has_no_bundle_navigation() -> None:
    state = ViewerState(
        [_entry("book.zip", "1.png"), _entry("book.zip", "2.png")],
        current_index=1,
    )

    assert not state.has_next_archive()
    assert not state.has_previous_archive()
    assert not state.move_next_archive()
    assert not state.move_previous_archive()
    assert state.current_index == 1


def test_bundle_navigation_wraps_between_container_starts() -> None:
    state = ViewerState(
        [
            _entry("first.zip", "1.png"),
            _entry("first.zip", "2.png"),
            _entry("second.zip", "1.png"),
        ],
        current_index=1,
    )

    assert state.move_next_archive()
    assert state.current_index == 2
    assert state.move_next_archive()
    assert state.current_index == 0
    assert state.move_previous_archive()
    assert state.current_index == 2
