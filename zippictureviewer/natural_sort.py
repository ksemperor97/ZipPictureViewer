from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable, TypeVar


_NUMBER_RE = re.compile(r"(\d+)")
T = TypeVar("T")


def natural_key(value: object) -> tuple[object, ...]:
    text = str(value).casefold()
    parts = _NUMBER_RE.split(text)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def natural_sorted(
    values: Iterable[T],
    key: Callable[[T], object] = lambda item: item,
) -> list[T]:
    return sorted(values, key=lambda item: natural_key(key(item)))
