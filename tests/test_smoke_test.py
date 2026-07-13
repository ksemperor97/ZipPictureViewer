from __future__ import annotations

from zippictureviewer.__main__ import main


def test_packaged_smoke_test_path(qapp, capsys) -> None:
    assert main(["--smoke-test"]) == 0
    assert "smoke test passed" in capsys.readouterr().out
