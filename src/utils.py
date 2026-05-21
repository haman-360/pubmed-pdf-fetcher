from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")


def read_pmids(path: Path) -> list[str]:
    pmids: list[str] = []
    seen: set[str] = set()

    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if not value.isdigit():
            raise ValueError(f"Invalid PMID: {value}")
        if value not in seen:
            pmids.append(value)
            seen.add(value)

    return pmids


def ensure_directories(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def sanitize_filename_part(value: str, max_length: int = 40) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("", value)
    cleaned = WHITESPACE.sub(" ", cleaned).strip()
    cleaned = cleaned.rstrip(". ")
    return cleaned[:max_length].rstrip() or "untitled"


def pdf_filename(pmid: str, title: str) -> str:
    return f"{pmid}_{sanitize_filename_part(title)}.pdf"


def write_csv(path: Path, rows: Iterable[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

