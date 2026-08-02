from __future__ import annotations

import csv
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")
PMID_LABEL = re.compile(r"\bPMID\s*[:：]?\s*(\d{1,9})\b", re.IGNORECASE)
PUBMED_URL = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,9})(?:/|\b)", re.IGNORECASE)
PMID_ONLY_LINE = re.compile(r"^\s*(?:PMID\s*[:：]?\s*)?(\d{1,9})\s*$", re.IGNORECASE)
DOCX_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_pmids(path: Path) -> list[str]:
    return extract_pmids(read_input_text(path))


def read_input_text(path: Path) -> str:
    """Read plain text or a Google Docs/Word .docx export."""
    if path.suffix.lower() != ".docx":
        return path.read_text(encoding="utf-8-sig")

    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Could not read DOCX file: {path}") from exc

    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid DOCX document XML: {path}") from exc

    paragraphs: list[str] = []
    for paragraph in root.iter(f"{DOCX_WORD_NAMESPACE}p"):
        paragraphs.append("".join(node.text or "" for node in paragraph.iter(f"{DOCX_WORD_NAMESPACE}t")))
    return "\n".join(paragraphs)


def read_clipboard() -> str:
    try:
        result = subprocess.run(
            ["pbpaste"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ValueError("Could not read the macOS clipboard with pbpaste") from exc
    return result.stdout


def extract_pmids(content: str) -> list[str]:
    """Extract explicit PMIDs without mistaking years or other article numbers for PMIDs."""
    candidates: list[tuple[int, str]] = []
    active_offset = 0

    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            active_offset += len(line)
            continue

        for pattern in (PMID_LABEL, PUBMED_URL):
            candidates.extend((active_offset + match.start(1), match.group(1)) for match in pattern.finditer(line))

        only_match = PMID_ONLY_LINE.fullmatch(line.rstrip("\r\n"))
        if only_match:
            candidates.append((active_offset + only_match.start(1), only_match.group(1)))
        active_offset += len(line)

    candidates.sort(key=lambda item: item[0])
    pmids: list[str] = []
    seen: set[str] = set()
    for _, pmid in candidates:
        normalized = pmid.lstrip("0") or "0"
        if normalized not in seen:
            pmids.append(normalized)
            seen.add(normalized)
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
