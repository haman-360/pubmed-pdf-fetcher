from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from pypdf import PdfReader

from .pubmed import ArticleMetadata
from .utils import TITLE_STOPWORDS, TITLE_WORD, pdf_filename


PMID_IN_TEXT = re.compile(r"\bPMID\s*[:：]?\s*(\d{1,9})\b", re.IGNORECASE)
LEADING_PMID = re.compile(r"^(\d{1,9})(?:[_ -]|$)")


@dataclass(frozen=True)
class PdfLibraryMatch:
    pmid: str
    original_name: str
    pdf_file: str
    match_method: str
    renamed: bool


@dataclass(frozen=True)
class PdfInspection:
    filename_text: str
    pdf_text: str
    metadata_title: str

    @property
    def combined_text(self) -> str:
        return " ".join((self.filename_text, self.metadata_title, self.pdf_text))


def reconcile_pdf_library(
    articles: Iterable[ArticleMetadata],
    pdf_dir: Path,
) -> tuple[dict[str, PdfLibraryMatch], list[str]]:
    article_list = list(articles)
    articles_by_pmid = {article.pmid: article for article in article_list}
    matches: dict[str, PdfLibraryMatch] = {}
    unmatched: list[str] = []

    for path in sorted(pdf_dir.glob("*.pdf")):
        if not is_pdf(path):
            unmatched.append(f"{path.name}: invalid PDF")
            continue

        match = match_pdf_to_article(path, article_list, articles_by_pmid)
        if match is None:
            unmatched.append(f"{path.name}: PMID/title could not be identified")
            continue
        article, method = match
        if article.pmid in matches:
            unmatched.append(f"{path.name}: duplicate PDF for PMID {article.pmid}")
            continue

        target = pdf_dir / pdf_filename(article.pmid, article.title)
        renamed = target != path
        if renamed:
            if target.exists():
                unmatched.append(f"{path.name}: rename target already exists ({target.name})")
                target = path
                renamed = False
            else:
                path.rename(target)

        matches[article.pmid] = PdfLibraryMatch(
            pmid=article.pmid,
            original_name=path.name,
            pdf_file=target.name,
            match_method=method,
            renamed=renamed,
        )

    return matches, unmatched


def match_pdf_to_article(
    path: Path,
    articles: list[ArticleMetadata],
    articles_by_pmid: dict[str, ArticleMetadata] | None = None,
) -> tuple[ArticleMetadata, str] | None:
    by_pmid = articles_by_pmid or {article.pmid: article for article in articles}
    leading_pmid = LEADING_PMID.match(path.stem)
    if leading_pmid and leading_pmid.group(1) in by_pmid:
        return by_pmid[leading_pmid.group(1)], "filename_pmid"

    inspection = inspect_pdf(path)
    explicit_pmids = PMID_IN_TEXT.findall(inspection.pdf_text[:20000])
    explicit_matches = [by_pmid[pmid] for pmid in explicit_pmids if pmid in by_pmid]
    if len({article.pmid for article in explicit_matches}) == 1:
        return explicit_matches[0], "pdf_text_pmid"

    normalized_filename = normalize_identifier(inspection.filename_text)
    normalized_pdf_text = normalize_identifier(
        " ".join((inspection.metadata_title, inspection.pdf_text[:30000]))
    )
    identifier_matches: list[tuple[ArticleMetadata, str]] = []
    for article in articles:
        for label, value in (("doi", article.doi), ("pmcid", article.pmcid), ("pii", article.pii)):
            identifier = normalize_identifier(value)
            if len(identifier) < 7:
                continue
            if identifier in normalized_filename:
                identifier_matches.append((article, f"filename_{label}"))
                break
            if identifier in normalized_pdf_text:
                identifier_matches.append((article, f"pdf_text_{label}"))
                break
    unique_identifier_matches = {
        article.pmid: (article, method) for article, method in identifier_matches
    }
    if len(unique_identifier_matches) == 1:
        return next(iter(unique_identifier_matches.values()))

    corpus_words = normalized_words(inspection.combined_text)
    scored: list[tuple[float, ArticleMetadata]] = []
    for article in articles:
        title_words = normalized_words(article.title)
        if len(title_words) < 3:
            continue
        overlap = len(title_words & corpus_words)
        coverage = overlap / len(title_words)
        if overlap >= 4 and coverage >= 0.60:
            scored.append((coverage, article))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.10:
        return None
    return scored[0][1], "title_similarity"


def inspect_pdf(path: Path, max_pages: int = 2) -> PdfInspection:
    metadata_title = ""
    extracted: list[str] = []
    try:
        reader = PdfReader(path)
        if reader.metadata and reader.metadata.title:
            metadata_title = str(reader.metadata.title)
        for page in reader.pages[:max_pages]:
            extracted.append(page.extract_text() or "")
    except Exception:
        pass
    return PdfInspection(
        filename_text=path.stem.replace("_", " "),
        metadata_title=metadata_title,
        pdf_text="\n".join(extracted),
    )


def normalized_words(value: str) -> set[str]:
    return {
        word.lower()
        for word in TITLE_WORD.findall(value)
        if word.lower() not in TITLE_STOPWORDS and len(word) > 1
    }


def normalize_identifier(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False
