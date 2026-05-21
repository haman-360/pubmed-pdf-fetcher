from __future__ import annotations

import argparse
from pathlib import Path

from .pdf_finder import PdfFinder
from .pubmed import PubMedClient, polite_pause
from .utils import ensure_directories, pdf_filename, read_pmids, write_csv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
PDF_DIR = PROJECT_ROOT / "pdf"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download legally available OA PDFs from a PMID list.")
    parser.add_argument("pmid_file", type=Path, help="Path to a text file containing one PMID per line.")
    args = parser.parse_args()

    ensure_directories(OUTPUT_DIR, PDF_DIR)
    pmids = read_pmids(args.pmid_file)
    if not pmids:
        print("No PMIDs found.")
        return 0

    pubmed = PubMedClient()
    finder = PdfFinder()

    metadata_rows: list[dict[str, str]] = []
    not_found_rows: list[dict[str, str]] = []

    print(f"Fetching metadata for {len(pmids)} PMID(s)...")
    articles = pubmed.fetch_metadata(pmids)

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
        if destination.exists() and destination.stat().st_size > 0:
            print(f"  Already exists: {destination.name}")
            continue

        result = finder.download_pdf(article, destination)
        if result.success:
            print(f"  Downloaded from {result.source}: {destination.name}")
        else:
            if destination.exists() and destination.stat().st_size == 0:
                destination.unlink()
            print(f"  Not found: {result.reason}")
            not_found_rows.append(
                {
                    "PMID": article.pmid,
                    "title": article.title,
                    "DOI": article.doi,
                    "publisher_url": article.publisher_url,
                    "reason": result.reason,
                }
            )

        polite_pause()

    write_csv(
        OUTPUT_DIR / "metadata.csv",
        metadata_rows,
        ["PMID", "title", "journal", "year", "DOI", "PMCID", "publisher_url"],
    )
    write_csv(
        OUTPUT_DIR / "not_found.csv",
        not_found_rows,
        ["PMID", "title", "DOI", "publisher_url", "reason"],
    )

    print(f"Done. Metadata: {OUTPUT_DIR / 'metadata.csv'}")
    print(f"Done. Not found: {OUTPUT_DIR / 'not_found.csv'}")
    print(f"PDF directory: {PDF_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

