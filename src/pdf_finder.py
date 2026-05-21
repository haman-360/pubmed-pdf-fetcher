from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests

from .pubmed import ArticleMetadata


PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",
}


@dataclass
class PdfResult:
    success: bool
    source: str = ""
    url: str = ""
    reason: str = ""


class PdfFinder:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "pubmed-pdf-downloader/0.1 (mailto:local-user@example.com)",
                "Accept": "application/pdf,application/json,text/html;q=0.8,*/*;q=0.5",
            }
        )
        self.unpaywall_email = os.getenv("UNPAYWALL_EMAIL", "")

    def download_pdf(self, metadata: ArticleMetadata, destination: Path) -> PdfResult:
        if metadata.pmcid:
            result = self._try_pmc(metadata.pmcid, destination)
            if result.success:
                return result

        if metadata.doi:
            result = self._try_unpaywall(metadata.doi, destination)
            if result.success:
                return result
            if result.reason:
                return result

        if not metadata.pmcid and not metadata.doi:
            return PdfResult(success=False, reason="No PMCID or DOI available")
        if metadata.doi and not self.unpaywall_email:
            return PdfResult(success=False, reason="PMC PDF not found and UNPAYWALL_EMAIL is not set")
        return PdfResult(success=False, reason="No legally available OA PDF found")

    def _try_pmc(self, pmcid: str, destination: Path) -> PdfResult:
        candidates = [
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/",
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/",
        ]

        last_reason = ""
        for url in candidates:
            result = self._download_if_pdf(url, destination, "PMC")
            if result.success:
                return result
            last_reason = result.reason

        return PdfResult(success=False, source="PMC", reason=last_reason or "PMC PDF not found")

    def _try_unpaywall(self, doi: str, destination: Path) -> PdfResult:
        if not self.unpaywall_email:
            return PdfResult(success=False, source="Unpaywall", reason="UNPAYWALL_EMAIL is not set")

        url = f"https://api.unpaywall.org/v2/{quote(doi, safe='')}"
        response = self.session.get(
            url,
            params={"email": self.unpaywall_email},
            timeout=self.timeout,
        )

        if response.status_code == 404:
            return PdfResult(success=False, source="Unpaywall", reason="DOI not found in Unpaywall")
        response.raise_for_status()

        data = response.json()
        pdf_url = self._best_unpaywall_pdf_url(data)
        if not pdf_url:
            return PdfResult(success=False, source="Unpaywall", reason="No OA PDF URL in Unpaywall")

        return self._download_if_pdf(pdf_url, destination, "Unpaywall")

    def _best_unpaywall_pdf_url(self, data: dict) -> str:
        best = data.get("best_oa_location") or {}
        if best.get("url_for_pdf"):
            return best["url_for_pdf"]

        for location in data.get("oa_locations") or []:
            if location.get("url_for_pdf"):
                return location["url_for_pdf"]

        return ""

    def _download_if_pdf(self, url: str, destination: Path, source: str) -> PdfResult:
        try:
            with self.session.get(url, timeout=self.timeout, stream=True, allow_redirects=True) as response:
                if response.status_code in {401, 403}:
                    return PdfResult(False, source=source, url=url, reason="PDF requires authentication")
                if response.status_code == 404:
                    return PdfResult(False, source=source, url=url, reason="PDF URL not found")
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                chunks = response.iter_content(chunk_size=8192)
                first_chunk = next(chunks, b"")

                if content_type not in PDF_CONTENT_TYPES and not first_chunk.startswith(b"%PDF"):
                    return PdfResult(False, source=source, url=url, reason=f"URL did not return a PDF ({content_type or 'unknown content type'})")

                with destination.open("wb") as handle:
                    handle.write(first_chunk)
                    for chunk in chunks:
                        if chunk:
                            handle.write(chunk)

            return PdfResult(True, source=source, url=url)
        except requests.RequestException as exc:
            return PdfResult(False, source=source, url=url, reason=f"Download failed: {exc}")
