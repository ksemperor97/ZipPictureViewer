from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .archive_metadata import ScanOptions
from .archive_scanner import scan_image_index


class ScanWorker(QObject):
    progress = Signal(int, str, int)
    finished = Signal(int, object)
    failed = Signal(int, str)

    def __init__(
        self,
        root: Path,
        generation: int,
        options: ScanOptions | None = None,
    ) -> None:
        super().__init__()
        self.root = root
        self.generation = generation
        self.options = options
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            result = scan_image_index(
                self.root,
                options=self.options,
                generation=self.generation,
                cancel_check=self._cancelled.is_set,
                progress_callback=self._report_progress,
            )
        except Exception as error:
            self.failed.emit(self.generation, str(error))
            return
        self.finished.emit(self.generation, result)

    def _report_progress(self, path: Path, count: int) -> None:
        self.progress.emit(self.generation, str(path), count)


@dataclass(frozen=True)
class _ScanJob:
    thread: QThread
    worker: ScanWorker


class ScanCoordinator(QObject):
    """Own scan threads and retire them only after their event loop exits."""

    progress = Signal(int, str, int)
    finished = Signal(int, object)
    failed = Signal(int, str)
    idle = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._jobs: dict[int, _ScanJob] = {}

    @property
    def active_count(self) -> int:
        return len(self._jobs)

    def start(
        self,
        root: Path,
        generation: int,
        options: ScanOptions | None = None,
    ) -> None:
        self.cancel_except(generation)
        thread = QThread()
        worker = ScanWorker(root, generation, options)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.finished.connect(self.finished)
        worker.failed.connect(self.failed)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(
            lambda completed_generation=generation: self._retire(
                completed_generation
            )
        )
        thread.finished.connect(thread.deleteLater)

        self._jobs[generation] = _ScanJob(thread, worker)
        thread.start()

    def cancel(self, generation: int) -> bool:
        job = self._jobs.get(generation)
        if job is None:
            return False
        job.worker.cancel()
        return True

    def cancel_except(self, generation: int) -> None:
        for job_generation, job in self._jobs.items():
            if job_generation != generation:
                job.worker.cancel()

    def cancel_all(self) -> None:
        for job in self._jobs.values():
            job.worker.cancel()

    @Slot(int)
    def _retire(self, generation: int) -> None:
        self._jobs.pop(generation, None)
        if not self._jobs:
            self.idle.emit()
