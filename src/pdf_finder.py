from __future__ import annotations

import os
from html.parser import HTMLParser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin
import xml.etree.ElementTree as ET

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
        reasons: list[str] = []

        if metadata.pmcid:
            result = self._try_pmc(metadata.pmcid, destination)
            if result.success:
                return result
            if result.reason:
                reasons.append(f"PMC: {result.reason}")

        if metadata.doi:
            result = self._try_unpaywall(metadata.doi, destination)
            if result.success:
                return result
            if result.reason:
                reasons.append(f"Unpaywall: {result.reason}")

        result = self._try_europe_pmc(metadata, destination)
        if result.success:
            return result
        if result.reason:
            reasons.append(f"Europe PMC: {result.reason}")

        if metadata.doi:
            result = self._try_publisher_pdf_candidates(metadata.doi, destination)
            if result.success:
                return result
            if result.reason:
                reasons.append(f"Publisher: {result.reason}")

        if not metadata.pmcid and not metadata.doi:
            return PdfResult(success=False, reason="No PMCID or DOI available")
        return PdfResult(success=False, reason="; ".join(reasons) or "No legally available OA PDF found")

    def _try_pmc(self, pmcid: str, destination: Path) -> PdfResult:
        oa_pdf_url = self._pmc_oa_pdf_url(pmcid)
        if oa_pdf_url:
            result = self._download_if_pdf(oa_pdf_url, destination, "PMC")
            if result.success:
                return result

        article_pdf_url = self._pmc_article_page_pdf_url(pmcid)
        if article_pdf_url:
            result = self._download_if_pdf(article_pdf_url, destination, "PMC")
            if result.success:
                return result

        candidates = [
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/",
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/",
            f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf",
        ]

        last_reason = ""
        for url in candidates:
            result = self._download_if_pdf(url, destination, "PMC")
            if result.success:
                return result
            last_reason = result.reason

        return PdfResult(success=False, source="PMC", reason=last_reason or "PMC PDF not found")

    def _pmc_oa_pdf_url(self, pmcid: str) -> str:
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
        try:
            response = self.session.get(url, params={"id": pmcid}, timeout=self.timeout)
            if response.status_code == 404:
                return ""
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError):
            return ""

        for link in root.findall(".//link"):
            if link.attrib.get("format", "").lower() == "pdf" and link.attrib.get("href"):
                return link.attrib["href"]
        return ""

    def _pmc_article_page_pdf_url(self, pmcid: str) -> str:
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return ""

        parser = PmcPdfLinkParser(url)
        parser.feed(response.text)
        return parser.pdf_url

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

    def _try_publisher_pdf_candidates(self, doi: str, destination: Path) -> PdfResult:
        candidates = self._publisher_pdf_candidates(doi)
        if not candidates:
            return PdfResult(success=False, source="Publisher", reason="No known publisher PDF candidate")

        last_reason = ""
        for url in candidates:
            result = self._download_if_pdf(url, destination, "Publisher")
            if result.success:
                return result
            last_reason = result.reason
            if result.reason == "PDF requires authentication":
                break

        return PdfResult(success=False, source="Publisher", reason=last_reason or "Publisher PDF not found")

    def _publisher_pdf_candidates(self, doi: str) -> list[str]:
        normalized = doi.strip()
        lower = normalized.lower()
        encoded = quote(normalized, safe="/")

        if lower.startswith("10.1111/"):
            return [f"https://onlinelibrary.wiley.com/doi/epdf/{encoded}"]

        return []

    def manual_pdf_candidates(self, doi: str) -> list[str]:
        return self._publisher_pdf_candidates(doi)

    def _try_europe_pmc(self, metadata: ArticleMetadata, destination: Path) -> PdfResult:
        queries: list[str] = []
        if metadata.doi:
            queries.append(f'DOI:"{metadata.doi}"')
        if metadata.pmid:
            queries.append(f"EXT_ID:{metadata.pmid} AND SRC:MED")

        for query in queries:
            pdf_url = self._europe_pmc_pdf_url(query)
            if not pdf_url:
                continue
            result = self._download_if_pdf(pdf_url, destination, "Europe PMC")
            if result.success:
                return result
            if result.reason == "PDF requires authentication":
                return result

        return PdfResult(success=False, source="Europe PMC", reason="No OA PDF URL in Europe PMC")

    def _europe_pmc_pdf_url(self, query: str) -> str:
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        try:
            response = self.session.get(
                url,
                params={"query": query, "format": "json", "resultType": "core", "pageSize": 1},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            return ""

        results = data.get("resultList", {}).get("result", [])
        if not results:
            return ""

        full_text_urls = results[0].get("fullTextUrlList", {}).get("fullTextUrl", [])
        for item in full_text_urls:
            url_value = item.get("url", "")
            style = item.get("documentStyle", "").lower()
            availability = item.get("availability", "").lower()
            if url_value and style == "pdf" and "free" in availability:
                return url_value

        for item in full_text_urls:
            url_value = item.get("url", "")
            style = item.get("documentStyle", "").lower()
            if url_value and (style == "pdf" or url_value.lower().split("?")[0].endswith(".pdf")):
                return url_value

        return ""

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
                    reason = f"URL did not return a PDF ({content_type or 'unknown content type'})"
                    if source == "Publisher" and content_type == "text/html":
                        reason = "Publisher returned HTML instead of PDF; manual browser check, CAPTCHA, or login may be required"
                    return PdfResult(False, source=source, url=url, reason=reason)

                with destination.open("wb") as handle:
                    handle.write(first_chunk)
                    for chunk in chunks:
                        if chunk:
                            handle.write(chunk)

            return PdfResult(True, source=source, url=url)
        except requests.RequestException as exc:
            return PdfResult(False, source=source, url=url, reason=f"Download failed: {exc}")


class PmcPdfLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.pdf_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.pdf_url:
            return

        attr_map = {key.lower(): value or "" for key, value in attrs}
        href = attr_map.get("href", "")
        if not href:
            return

        lower_href = href.lower()
        classes = attr_map.get("class", "").lower()
        aria_label = attr_map.get("aria-label", "").lower()

        if (
            lower_href.endswith(".pdf")
            or "/pdf/" in lower_href
            or "pdf" in classes
            or "pdf" in aria_label
        ):
            self.pdf_url = urljoin(self.base_url, href)
