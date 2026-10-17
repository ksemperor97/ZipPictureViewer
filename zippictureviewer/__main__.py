from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zip-picture-viewer")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="validate the packaged Qt runtime and exit",
    )
    # Used by the end-to-end tests to drive a real app process.
    parser.add_argument("--automation-handshake", help=argparse.SUPPRESS)
    arguments = list(sys.argv[1:] if argv is None else argv)
    options, qt_arguments = parser.parse_known_args(arguments)
    try:
        if options.smoke_test:
            from .smoke_test import run_smoke_test

            return run_smoke_test()
        from .ui import run_app
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print(
                "PySide6가 설치되어 있지 않습니다. "
                "먼저 `pip install -e .`를 실행하세요."
            )
            return 1
        raise

    return run_app(
        [sys.argv[0], *qt_arguments],
        automation_handshake=options.automation_handshake,
    )


if __name__ == "__main__":
    raise SystemExit(main())
