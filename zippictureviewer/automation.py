"""Loopback control channel used by the end-to-end tests.

The channel exists only when the app is started with ``--automation-handshake``
and an authentication key in ``ZIP_PICTURE_VIEWER_AUTOMATION_KEY``. Commands
arrive on a background thread and are executed on the GUI thread, where they
inject real Qt input events into the running window.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from multiprocessing.connection import Listener
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from .automation_commands import AutomationCommands


AUTOMATION_KEY_ENV = "ZIP_PICTURE_VIEWER_AUTOMATION_KEY"


@dataclass
class _Request:
    command: dict[str, Any]
    done: threading.Event = field(default_factory=threading.Event)
    reply: dict[str, Any] = field(default_factory=dict)


class AutomationServer(QObject):
    _request_received = Signal(object)

    def __init__(self, window, handshake_path: Path) -> None:
        super().__init__(window)
        key = os.environ.get(AUTOMATION_KEY_ENV)
        if not key:
            raise RuntimeError(f"{AUTOMATION_KEY_ENV} is required for automation")
        self._commands = AutomationCommands(window)
        self._listener = Listener(("127.0.0.1", 0), authkey=bytes.fromhex(key))
        # Emitted from the listener thread; Qt queues it onto the GUI thread.
        self._request_received.connect(self._execute)
        self._thread = threading.Thread(
            target=self._serve,
            name="automation",
            daemon=True,
        )
        self._thread.start()
        _write_handshake(handshake_path, self._listener.address[1])

    def _serve(self) -> None:
        with self._listener.accept() as connection:
            while True:
                try:
                    command = connection.recv()
                except (EOFError, OSError):
                    return
                request = _Request(command)
                self._request_received.emit(request)
                request.done.wait()
                connection.send(request.reply)

    def _execute(self, request: _Request) -> None:
        try:
            request.reply = {"result": self._commands.run(request.command)}
        except Exception as exc:  # reported to the test instead of crashing the app
            request.reply = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            request.done.set()


def _write_handshake(path: Path, port: int) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"port": port, "pid": os.getpid()}))
    os.replace(temporary, path)
