"""Launch the real viewer process and drive it through its automation channel.

By default the app runs from source with the current interpreter. Set
``ZPV_E2E_APP`` to a packaged executable (``.app/Contents/MacOS/...`` or
``ZipPictureViewer.exe``) to run the same scenarios against a built bundle.
The Qt platform is inherited, so windows appear on screen unless
``QT_QPA_PLATFORM=offscreen`` is set (as CI does).
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from multiprocessing.connection import Client
from pathlib import Path
from typing import Any


STARTUP_TIMEOUT = 30.0
DEFAULT_TIMEOUT = 10.0


class AutomationError(RuntimeError):
    pass


class ViewerApp:
    def __init__(
        self,
        work_dir: Path,
        config_dir: Path,
        args: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.work_dir = work_dir
        self.config_dir = config_dir
        self.args = args
        self.extra_env = extra_env or {}
        self.log_path = work_dir / "app.log"
        self.process: subprocess.Popen | None = None
        self._connection = None

    def start(self) -> ViewerApp:
        handshake = self.work_dir / f"handshake-{secrets.token_hex(4)}.json"
        key = secrets.token_hex(16)
        env = dict(os.environ)
        env["ZIP_PICTURE_VIEWER_CONFIG_DIR"] = str(self.config_dir)
        env["ZIP_PICTURE_VIEWER_AUTOMATION_KEY"] = key
        env.update(self.extra_env)
        command = [*app_command(), "--automation-handshake", str(handshake), *self.args]
        with self.log_path.open("ab") as log:
            self.process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        port = self._wait_for_handshake(handshake)
        self._connection = Client(("127.0.0.1", port), authkey=bytes.fromhex(key))
        return self

    def call(self, name: str, **params: Any) -> Any:
        self._connection.send({"name": name, "params": params})
        reply = self._connection.recv()
        if "error" in reply:
            raise AutomationError(f"{name} failed: {reply['error']}\n{self.log_tail()}")
        return reply["result"]

    def state(self) -> dict[str, Any]:
        return self.call("state")

    def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        description: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        state = self.state()
        while not predicate(state):
            if time.monotonic() > deadline:
                raise AssertionError(
                    f"Timed out waiting for {description}.\n"
                    f"Last state: {json.dumps(state, ensure_ascii=False, indent=2)}\n"
                    f"{self.log_tail()}"
                )
            time.sleep(0.05)
            state = self.state()
        return state

    def wait_for_image(self, archive: str, member: str) -> dict[str, Any]:
        return self.wait_for(
            lambda s: s["archive"] == archive and s["member"] == member and s["has_image"],
            f"{archive} | {member} to be displayed",
        )

    def wait_for_idle(self) -> dict[str, Any]:
        return self.wait_for(lambda s: not s["scanning"], "scan to finish")

    def key(self, key: str, *modifiers: str) -> None:
        # Window shortcuts only fire in the active window; a freshly launched
        # or backgrounded app has to be brought forward first, like a click.
        if not self.state()["active"]:
            self.call("activate")
            self.wait_for(lambda s: s["active"], "window activation")
        self.call("key", key=key, modifiers=list(modifiers))

    def drop(self, *paths: Path, x: float = 0.5, y: float = 0.5) -> bool:
        result = self.call("drop", paths=[str(path) for path in paths], x=x, y=y)
        return result["accepted"]

    def click(self, button: str) -> None:
        # Moving the mouse reveals the auto-hiding controls, as for a user.
        self.call("move_mouse", x=0.5, y=0.5)
        self.call("click", button=button)

    def pixel(self, x: float = 0.5, y: float = 0.5) -> str:
        return self.call("pixel", x=x, y=y)

    def close(self, timeout: float = DEFAULT_TIMEOUT) -> int:
        self.call("close")
        return self.wait_for_exit(timeout)

    def wait_for_exit(self, timeout: float = DEFAULT_TIMEOUT) -> int:
        self._disconnect()
        try:
            return self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(f"App did not exit.\n{self.log_tail()}") from exc

    def kill(self) -> None:
        self._disconnect()
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=DEFAULT_TIMEOUT)

    def log_tail(self, lines: int = 30) -> str:
        if not self.log_path.exists():
            return "(no app log)"
        text = self.log_path.read_text(errors="replace").splitlines()[-lines:]
        return "App log:\n" + "\n".join(text)

    def _wait_for_handshake(self, handshake: Path) -> int:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while not handshake.exists():
            if self.process.poll() is not None:
                raise AssertionError(f"App exited during startup.\n{self.log_tail()}")
            if time.monotonic() > deadline:
                self.kill()
                raise AssertionError(f"App did not start.\n{self.log_tail()}")
            time.sleep(0.05)
        return json.loads(handshake.read_text())["port"]

    def _disconnect(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def app_command() -> list[str]:
    packaged = os.environ.get("ZPV_E2E_APP")
    if packaged:
        return [packaged]
    return [sys.executable, "-m", "zippictureviewer"]
