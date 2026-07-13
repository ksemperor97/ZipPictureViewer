from __future__ import annotations

from pathlib import Path
from threading import Event

from zippictureviewer.models import ScanResult
from zippictureviewer.scan_worker import ScanCoordinator, ScanWorker


def test_scan_worker_reports_generation_and_result(tmp_path: Path, qtbot) -> None:
    worker = ScanWorker(tmp_path, generation=7)

    with qtbot.waitSignal(worker.finished, timeout=1000) as signal:
        worker.run()

    generation, result = signal.args
    assert generation == 7
    assert result.generation == 7
    assert result.entries == []


def test_cancelled_scan_marks_result_cancelled(tmp_path: Path, qtbot) -> None:
    worker = ScanWorker(tmp_path, generation=3)
    worker.cancel()

    with qtbot.waitSignal(worker.finished, timeout=1000) as signal:
        worker.run()

    _, result = signal.args
    assert result.cancelled


def test_scan_coordinator_keeps_only_the_latest_pending_request(
    tmp_path: Path,
    qtbot,
    monkeypatch,
) -> None:
    import zippictureviewer.scan_worker as scan_worker

    started: list[int] = []
    release_first = Event()

    def controlled_scan(
        root,
        *,
        options=None,
        generation=0,
        cancel_check=None,
        progress_callback=None,
    ) -> ScanResult:
        started.append(generation)
        if generation == 1:
            release_first.wait(5)
        return ScanResult(
            generation=generation,
            cancelled=bool(cancel_check and cancel_check()),
        )

    monkeypatch.setattr(scan_worker, "scan_image_index", controlled_scan)
    coordinator = ScanCoordinator()
    coordinator.start(tmp_path, 1)
    qtbot.waitUntil(lambda: started == [1], timeout=2000)

    coordinator.start(tmp_path, 2)
    coordinator.start(tmp_path, 3)

    assert coordinator.active_count == 1
    assert coordinator.pending_generation == 3
    release_first.set()
    qtbot.waitUntil(lambda: started == [1, 3], timeout=2000)
    qtbot.waitUntil(lambda: coordinator.active_count == 0, timeout=2000)


def test_cancelling_a_pending_scan_emits_a_cancelled_result(
    tmp_path: Path,
    qtbot,
    monkeypatch,
) -> None:
    import zippictureviewer.scan_worker as scan_worker

    first_started = Event()
    release_first = Event()

    def controlled_scan(
        root,
        *,
        options=None,
        generation=0,
        cancel_check=None,
        progress_callback=None,
    ) -> ScanResult:
        first_started.set()
        release_first.wait(5)
        return ScanResult(generation=generation, cancelled=True)

    monkeypatch.setattr(scan_worker, "scan_image_index", controlled_scan)
    coordinator = ScanCoordinator()
    coordinator.start(tmp_path, 1)
    qtbot.waitUntil(first_started.is_set, timeout=2000)
    coordinator.start(tmp_path, 2)

    with qtbot.waitSignal(coordinator.finished, timeout=1000) as signal:
        assert coordinator.cancel(2)

    generation, result = signal.args
    assert generation == 2
    assert result.cancelled
    release_first.set()
    qtbot.waitUntil(lambda: coordinator.active_count == 0, timeout=2000)
