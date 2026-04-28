from __future__ import annotations


def main() -> int:
    try:
        from .ui import run_app
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print("PySide6가 설치되어 있지 않습니다. 먼저 `pip install -e .`를 실행하세요.")
            return 1
        raise

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
