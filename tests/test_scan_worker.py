from __future__ import annotations

from pathlib import Path

from zippictureviewer.scan_worker import ScanWorker


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
