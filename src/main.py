from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

from .pdf_finder import PdfFinder
from .pubmed import PubMedClient, polite_pause
from .utils import extract_pmids, ensure_directories, pdf_filename, read_clipboard, read_pmids, write_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
PDF_DIR = PROJECT_ROOT / "pdf"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download legally available OA PDFs from a PMID list.")
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "pmid_file",
        type=Path,
        nargs="?",
        default=PROJECT_ROOT / "input" / "pmids.txt",
        help="Text or .docx file containing PMIDs (default: input/pmids.txt).",
    )
    input_group.add_argument(
        "--clipboard",
        action="store_true",
        help="Extract PMIDs from the macOS clipboard (useful after copying a Google Doc).",
    )
    args = parser.parse_args()

    ensure_directories(OUTPUT_DIR, PDF_DIR)
    try:
        pmids = extract_pmids(read_clipboard()) if args.clipboard else read_pmids(args.pmid_file)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not pmids:
        print("No explicit PMIDs found. Use lines such as 'PMID: 31452104' or a PubMed URL.")
        return 0

    pubmed = PubMedClient()
    finder = PdfFinder()

    metadata_rows: list[dict[str, str]] = []
    not_found_rows: list[dict[str, str]] = []
    manual_check_rows: list[dict[str, str]] = []
    history_rows: list[dict[str, str]] = []
    downloaded_count = 0
    existing_count = 0

    print(f"Fetching metadata for {len(pmids)} PMID(s)...")
    try:
        articles = pubmed.fetch_metadata(pmids)
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"Could not fetch PubMed metadata: {exc}")
        return 1

    for index, article in enumerate(articles, start=1):
        print(f"[{index}/{len(articles)}] PMID {article.pmid}: {article.title or 'title unavailable'}")
        metadata_rows.append(article.as_csv_row())

        if not article.title:
            not_found_rows.append(
                {
                    "PMID": article.pmid,
                    "title": article.title,
                    "DOI": article.doi,
                    "publisher_url": article.publisher_url,
                    "reason": "Metadata not found",
                }
            )
            continue

        destination = PDF_DIR / pdf_filename(article.pmid, article.title)
        if finder.is_pdf_file(destination):
            print(f"  Already exists: {destination.name}")
            existing_count += 1
            history_rows.append(
                history_row(
                    article.pmid,
                    article.title,
                    "already_exists",
                    pdf_file=destination.name,
                )
            )
            continue

        result = finder.download_pdf(article, destination)
        if result.success:
            print(f"  Downloaded from {result.source}: {destination.name}")
            downloaded_count += 1
            history_rows.append(
                history_row(
                    article.pmid,
                    article.title,
                    "downloaded",
                    pdf_file=destination.name,
                    source=result.source,
                    url=result.url,
                )
            )
        else:
            if destination.exists() and destination.stat().st_size == 0:
                destination.unlink()
            print(f"  Not found: {result.reason}")
            for manual_url in finder.manual_pdf_candidates_for_article(article):
                manual_check_rows.append(
                    {
                        "PMID": article.pmid,
                        "title": article.title,
                        "DOI": article.doi,
                        "manual_url": manual_url,
                        "note": "Open manually in a browser if publisher requires CAPTCHA or login.",
                    }
                )
            not_found_rows.append(
                {
                    "PMID": article.pmid,
                    "title": article.title,
                    "DOI": article.doi,
                    "publisher_url": article.publisher_url,
                    "reason": result.reason,
                }
            )
            history_rows.append(
                history_row(
                    article.pmid,
                    article.title,
                    "not_found",
                    reason=result.reason,
                    url=article.publisher_url,
                )
            )

        polite_pause()

    write_csv(
        OUTPUT_DIR / "metadata.csv",
        metadata_rows,
        ["PMID", "title", "journal", "year", "DOI", "PMCID", "PII", "publisher_url"],
    )
    write_csv(
        OUTPUT_DIR / "not_found.csv",
        not_found_rows,
        ["PMID", "title", "DOI", "publisher_url", "reason"],
    )
    write_csv(
        OUTPUT_DIR / "manual_check.csv",
        manual_check_rows,
        ["PMID", "title", "DOI", "manual_url", "note"],
    )
    append_history_csv(OUTPUT_DIR / "history.csv", history_rows)

    print(f"Done. Metadata: {OUTPUT_DIR / 'metadata.csv'}")
    print(f"Done. Not found: {OUTPUT_DIR / 'not_found.csv'}")
    print(f"Done. Manual check: {OUTPUT_DIR / 'manual_check.csv'}")
    print(f"Done. History: {OUTPUT_DIR / 'history.csv'}")
    print(f"PDF directory: {PDF_DIR}")
    print("")
    print("Summary:")
    print(f"  Articles processed: {len(articles)}")
    print(f"  PDFs downloaded: {downloaded_count}")
    print(f"  PDFs already present: {existing_count}")
    print(f"  PDFs not found: {len(not_found_rows)}")
    return 0


def history_row(
    pmid: str,
    title: str,
    status: str,
    pdf_file: str = "",
    source: str = "",
    url: str = "",
    reason: str = "",
) -> dict[str, str]:
    run_date = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "date": run_date,
        "status": status,
        "PMID": pmid,
        "title": title,
        "pdf_file": pdf_file,
        "source": source,
        "url": url,
        "reason": reason,
    }


def append_history_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return

    fieldnames = ["date", "status", "PMID", "title", "pdf_file", "source", "url", "reason"]
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
