from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from zippictureviewer.archive_scanner import scan_image_index


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark a synthetic ZIP/image corpus")
    parser.add_argument("--archives", type=int, default=1000)
    parser.add_argument("--images-per-archive", type=int, default=10)
    parser.add_argument("--output", type=Path)
    return parser


def create_corpus(root: Path, archives: int, images_per_archive: int) -> None:
    for archive_index in range(archives):
        archive_path = root / f"book-{archive_index:05d}.zip"
        with ZipFile(archive_path, "w", ZIP_STORED) as archive:
            for image_index in range(images_per_archive):
                archive.writestr(
                    f"page-{image_index:04d}.png",
                    b"synthetic image metadata benchmark",
                )


def benchmark(archives: int, images_per_archive: int) -> dict[str, int | float]:
    if archives <= 0 or images_per_archive <= 0:
        raise ValueError("archive and image counts must be positive")
    with tempfile.TemporaryDirectory(prefix="zip-picture-viewer-benchmark-") as temp:
        root = Path(temp)
        create_started = time.perf_counter()
        create_corpus(root, archives, images_per_archive)
        create_seconds = time.perf_counter() - create_started

        tracemalloc.start()
        scan_started = time.perf_counter()
        result = scan_image_index(root)
        scan_seconds = time.perf_counter() - scan_started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    return {
        "archives": archives,
        "images_per_archive": images_per_archive,
        "expected_images": archives * images_per_archive,
        "indexed_images": len(result.entries),
        "issues": len(result.issues),
        "create_seconds": round(create_seconds, 3),
        "scan_seconds": round(scan_seconds, 3),
        "peak_python_bytes": peak_bytes,
    }


def main() -> int:
    args = build_parser().parse_args()
    metrics = benchmark(args.archives, args.images_per_archive)
    payload = json.dumps(metrics, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if metrics["indexed_images"] == metrics["expected_images"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
