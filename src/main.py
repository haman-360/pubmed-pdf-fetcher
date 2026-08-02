from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import requests

from .pdf_finder import PdfFinder
from .pdf_library import PdfLibraryMatch, reconcile_pdf_library
from .pubmed import ArticleMetadata, PubMedClient, polite_pause
from .utils import extract_pmids, ensure_directories, pdf_filename, read_clipboard, read_pmids, write_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
PDF_DIR = PROJECT_ROOT / "pdf"
METADATA_FIELDS = [
    "PMID", "title", "journal", "year", "volume", "DOI", "PMCID", "PII",
    "publisher_url", "free_full_text_url", "pdf_status", "pdf_file", "pdf_source",
    "pdf_match_method",
]
NOT_FOUND_FIELDS = [
    "PMID", "title", "DOI", "publisher_url", "reason",
    "manual_priority", "manual_status", "manual_url",
]
MANUAL_CHECK_FIELDS = [
    "priority", "PMID", "title", "DOI", "status", "evidence", "manual_url", "note",
]


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
    input_group.add_argument(
        "--sync-library",
        action="store_true",
        help="Match and rename existing files in pdf/, then update output CSV files without downloading.",
    )
    args = parser.parse_args()

    ensure_directories(OUTPUT_DIR, PDF_DIR)
    if args.sync_library:
        return sync_existing_library()
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

    library_matches, unmatched_pdfs = reconcile_pdf_library(articles, PDF_DIR)
    print(f"Matched {len(library_matches)} existing PDF(s) in {PDF_DIR}.")
    for match in library_matches.values():
        if match.renamed:
            print(f"  Renamed: {match.original_name} -> {match.pdf_file}")
    for message in unmatched_pdfs:
        print(f"  Unmatched: {message}")

    for index, article in enumerate(articles, start=1):
        print(f"[{index}/{len(articles)}] PMID {article.pmid}: {article.title or 'title unavailable'}")
        metadata_row = article.as_csv_row()
        metadata_rows.append(metadata_row)

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
            metadata_row["pdf_status"] = "metadata_not_found"
            continue

        library_match = library_matches.get(article.pmid)
        if library_match:
            print(f"  Available in pdf/: {library_match.pdf_file}")
            existing_count += 1
            set_pdf_metadata(metadata_row, library_match)
            history_rows.append(
                history_row(
                    article.pmid,
                    article.title,
                    "synced_existing",
                    pdf_file=library_match.pdf_file,
                    source="pdf_folder_sync",
                    reason=f"Matched by {library_match.match_method}",
                )
            )
            continue

        destination = PDF_DIR / pdf_filename(article.pmid, article.title)
        if finder.is_pdf_file(destination):
            print(f"  Already exists: {destination.name}")
            existing_count += 1
            metadata_row.update(
                {
                    "pdf_status": "available",
                    "pdf_file": destination.name,
                    "pdf_source": "pdf_folder",
                    "pdf_match_method": "expected_filename",
                }
            )
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
            metadata_row.update(
                {
                    "pdf_status": "downloaded",
                    "pdf_file": destination.name,
                    "pdf_source": result.source,
                    "pdf_match_method": "automatic_download",
                }
            )
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
            manual_candidates = finder.manual_check_candidates_for_article(article)
            if manual_candidates:
                first_candidate = manual_candidates[0]
                print(f"  Manual check: {first_candidate.status}: {first_candidate.url}")
            for candidate in manual_candidates:
                manual_check_rows.append(
                    {
                        "priority": candidate.priority,
                        "PMID": article.pmid,
                        "title": article.title,
                        "DOI": article.doi,
                        "status": candidate.status,
                        "evidence": candidate.evidence,
                        "manual_url": candidate.url,
                        "note": "ブラウザでURLを開き、PDFリンクまたはダウンロードボタンを確認してください。",
                    }
                )
            best_manual = manual_candidates[0] if manual_candidates else None
            not_found_rows.append(
                {
                    "PMID": article.pmid,
                    "title": article.title,
                    "DOI": article.doi,
                    "publisher_url": article.publisher_url,
                    "reason": result.reason,
                    "manual_priority": best_manual.priority if best_manual else "",
                    "manual_status": best_manual.status if best_manual else "",
                    "manual_url": best_manual.url if best_manual else "",
                }
            )
            metadata_row["pdf_status"] = "not_found"
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
        METADATA_FIELDS,
    )
    write_csv(
        OUTPUT_DIR / "not_found.csv",
        not_found_rows,
        NOT_FOUND_FIELDS,
    )
    manual_check_rows.sort(key=lambda row: row["priority"])
    write_csv(
        OUTPUT_DIR / "manual_check.csv",
        manual_check_rows,
        MANUAL_CHECK_FIELDS,
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


def sync_existing_library() -> int:
    metadata_path = OUTPUT_DIR / "metadata.csv"
    if not metadata_path.exists():
        print(f"Cannot sync: metadata file not found: {metadata_path}")
        return 1

    metadata_rows = read_csv_rows(metadata_path)
    articles = [article_from_csv_row(row) for row in metadata_rows if row.get("PMID")]
    matches, unmatched = reconcile_pdf_library(articles, PDF_DIR)

    history_rows: list[dict[str, str]] = []
    article_by_pmid = {article.pmid: article for article in articles}
    for row in metadata_rows:
        match = matches.get(row.get("PMID", ""))
        if not match:
            continue
        was_already_synced = (
            row.get("pdf_status") == "available"
            and row.get("pdf_file") == match.pdf_file
        )
        if was_already_synced:
            continue
        set_pdf_metadata(row, match)
        article = article_by_pmid[match.pmid]
        history_rows.append(
            history_row(
                article.pmid,
                article.title,
                "synced_existing",
                pdf_file=match.pdf_file,
                source="pdf_folder_sync",
                reason=f"Matched by {match.match_method}",
            )
        )

    matched_pmids = set(matches)
    write_csv(metadata_path, metadata_rows, METADATA_FIELDS)
    rebuild_manual_output_files(articles, matched_pmids)
    append_history_csv(OUTPUT_DIR / "history.csv", history_rows)

    print(f"Synchronized {len(matches)} PDF(s).")
    for match in matches.values():
        action = "renamed and matched" if match.renamed else "matched"
        print(f"  PMID {match.pmid}: {action}: {match.pdf_file} ({match.match_method})")
    for message in unmatched:
        print(f"  Unmatched: {message}")
    print(f"Updated: {metadata_path}")
    print(f"Updated: {OUTPUT_DIR / 'not_found.csv'}")
    print(f"Updated: {OUTPUT_DIR / 'manual_check.csv'}")
    print(f"Updated: {OUTPUT_DIR / 'history.csv'}")
    return 0


def set_pdf_metadata(row: dict[str, str], match: PdfLibraryMatch) -> None:
    row.update(
        {
            "pdf_status": "available",
            "pdf_file": match.pdf_file,
            "pdf_source": "pdf_folder_sync",
            "pdf_match_method": match.match_method,
        }
    )


def article_from_csv_row(row: dict[str, str]) -> ArticleMetadata:
    return ArticleMetadata(
        pmid=row.get("PMID", ""),
        title=row.get("title", ""),
        journal=row.get("journal", ""),
        year=row.get("year", ""),
        doi=row.get("DOI", ""),
        pmcid=row.get("PMCID", ""),
        pii=row.get("PII", ""),
        publisher_url=row.get("publisher_url", ""),
        volume=row.get("volume", ""),
        free_full_text_url=row.get("free_full_text_url", ""),
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def rebuild_manual_output_files(
    articles: list[ArticleMetadata], matched_pmids: set[str]
) -> None:
    not_found_path = OUTPUT_DIR / "not_found.csv"
    existing_not_found = {
        row.get("PMID", ""): row
        for row in read_csv_rows(not_found_path)
    } if not_found_path.exists() else {}
    finder = PdfFinder()
    not_found_rows: list[dict[str, str]] = []
    manual_rows: list[dict[str, str]] = []

    for article in articles:
        if article.pmid in matched_pmids or article.pmid not in existing_not_found:
            continue
        candidates = finder.manual_check_candidates_for_article(article)
        for candidate in candidates:
            manual_rows.append(
                {
                    "priority": candidate.priority,
                    "PMID": article.pmid,
                    "title": article.title,
                    "DOI": article.doi,
                    "status": candidate.status,
                    "evidence": candidate.evidence,
                    "manual_url": candidate.url,
                    "note": "ブラウザでURLを開き、PDFリンクまたはダウンロードボタンを確認してください。",
                }
            )

        row = existing_not_found[article.pmid]
        best = candidates[0] if candidates else None
        row.update(
            {
                "manual_priority": best.priority if best else "",
                "manual_status": best.status if best else "",
                "manual_url": best.url if best else "",
            }
        )
        not_found_rows.append(row)

    manual_rows.sort(key=lambda row: row["priority"])
    write_csv(not_found_path, not_found_rows, NOT_FOUND_FIELDS)
    write_csv(OUTPUT_DIR / "manual_check.csv", manual_rows, MANUAL_CHECK_FIELDS)


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
