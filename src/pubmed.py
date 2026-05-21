from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class ArticleMetadata:
    pmid: str
    title: str = ""
    journal: str = ""
    year: str = ""
    doi: str = ""
    pmcid: str = ""
    publisher_url: str = ""

    def as_csv_row(self) -> dict[str, str]:
        return {
            "PMID": self.pmid,
            "title": self.title,
            "journal": self.journal,
            "year": self.year,
            "DOI": self.doi,
            "PMCID": self.pmcid,
            "publisher_url": self.publisher_url,
        }


class PubMedClient:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.api_key = os.getenv("NCBI_API_KEY", "")

    def fetch_metadata(self, pmids: list[str]) -> list[ArticleMetadata]:
        if not pmids:
            return []

        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        response = self.session.get(
            f"{EUTILS_BASE}/efetch.fcgi",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()

        root = ET.fromstring(response.content)
        records = [self._parse_article(article) for article in root.findall(".//PubmedArticle")]
        found = {record.pmid for record in records}

        for pmid in pmids:
            if pmid not in found:
                records.append(ArticleMetadata(pmid=pmid))

        order = {pmid: index for index, pmid in enumerate(pmids)}
        return sorted(records, key=lambda record: order.get(record.pmid, len(order)))

    def _parse_article(self, article: ET.Element) -> ArticleMetadata:
        pmid = text(article.find(".//MedlineCitation/PMID"))
        title = flatten_text(article.find(".//ArticleTitle"))
        journal = text(article.find(".//Journal/Title")) or text(article.find(".//Journal/ISOAbbreviation"))
        year = extract_year(article)
        doi = extract_article_id(article, "doi")
        pmcid = normalize_pmcid(extract_article_id(article, "pmc"))
        publisher_url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        return ArticleMetadata(
            pmid=pmid,
            title=title,
            journal=journal,
            year=year,
            doi=doi,
            pmcid=pmcid,
            publisher_url=publisher_url,
        )


def text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def flatten_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def extract_article_id(article: ET.Element, id_type: str) -> str:
    for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType", "").lower() == id_type:
            return text(article_id)
    return ""


def normalize_pmcid(value: str) -> str:
    if not value:
        return ""
    return value if value.upper().startswith("PMC") else f"PMC{value}"


def extract_year(article: ET.Element) -> str:
    paths = [
        ".//Journal/JournalIssue/PubDate/Year",
        ".//ArticleDate/Year",
        ".//DateCompleted/Year",
        ".//DateRevised/Year",
    ]
    for path in paths:
        value = text(article.find(path))
        if value:
            return value

    medline_date = text(article.find(".//Journal/JournalIssue/PubDate/MedlineDate"))
    for token in medline_date.split():
        if token[:4].isdigit():
            return token[:4]
    return ""


def polite_pause() -> None:
    time.sleep(0.34)

