#!/usr/bin/env python3
"""Write or verify a sha256sum-compatible checksum sidecar for an artifact."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def checksum_sidecar_path(artifact: Path) -> Path:
    return Path(f"{artifact}.sha256")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum_sidecar(artifact: Path) -> Path:
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise ValueError(f"Artifact does not exist: {artifact}")
    sidecar = checksum_sidecar_path(artifact)
    sidecar.write_text(
        f"{sha256_file(artifact)}  {artifact.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    return sidecar


def check_checksum_sidecar(artifact: Path, sidecar: Path | None = None) -> list[str]:
    artifact = artifact.resolve()
    sidecar = (sidecar or checksum_sidecar_path(artifact)).resolve()
    if not artifact.is_file():
        return [f"Artifact does not exist: {artifact}"]
    try:
        contents = sidecar.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return [f"Cannot read checksum sidecar {sidecar}: {exc}"]

    parts = contents.split("  ", maxsplit=1)
    if len(parts) != 2:
        return [f"Checksum sidecar has invalid format: {sidecar}"]
    expected_hash, expected_name = parts
    errors: list[str] = []
    if SHA256_PATTERN.fullmatch(expected_hash) is None:
        errors.append(f"Checksum sidecar contains an invalid SHA-256: {expected_hash!r}")
    if expected_name != artifact.name:
        errors.append(f"Checksum sidecar names {expected_name!r}; expected {artifact.name!r}")
    actual_hash = sha256_file(artifact)
    if expected_hash != actual_hash:
        errors.append(f"Checksum mismatch for {artifact.name}: {expected_hash} != {actual_hash}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        sidecar = (
            write_checksum_sidecar(args.artifact)
            if args.write
            else args.sidecar or checksum_sidecar_path(args.artifact)
        )
        errors = check_checksum_sidecar(args.artifact, sidecar)
    except (OSError, ValueError) as exc:
        print(f"release artifact check failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Validated {args.artifact} with {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
