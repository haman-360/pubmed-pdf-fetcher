from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

from src.pdf_library import reconcile_pdf_library
from src.pubmed import ArticleMetadata
from src.utils import pdf_filename


def create_pdf(path: Path, title: str) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": title})
    with path.open("wb") as handle:
        writer.write(handle)


class PdfLibraryTests(unittest.TestCase):
    def test_matches_pdf_metadata_title_and_renames_file(self) -> None:
        title = "Gastrointestinal manifestations during oral immunotherapy in pediatric allergy"
        article = ArticleMetadata(pmid="42430571", title=title, doi="10.1111/pai.70417")

        with tempfile.TemporaryDirectory() as directory:
            pdf_dir = Path(directory)
            original = pdf_dir / "PAI-37-e70417.pdf"
            create_pdf(original, title)

            matches, unmatched = reconcile_pdf_library([article], pdf_dir)

            expected_name = pdf_filename(article.pmid, article.title)
            self.assertEqual(unmatched, [])
            self.assertEqual(matches[article.pmid].match_method, "title_similarity")
            self.assertTrue(matches[article.pmid].renamed)
            self.assertTrue((pdf_dir / expected_name).exists())
            self.assertFalse(original.exists())

    def test_unmatched_pdf_is_not_renamed(self) -> None:
        article = ArticleMetadata(pmid="1", title="Completely different article title")

        with tempfile.TemporaryDirectory() as directory:
            pdf_dir = Path(directory)
            original = pdf_dir / "unknown.pdf"
            create_pdf(original, "Unrelated document")

            matches, unmatched = reconcile_pdf_library([article], pdf_dir)

            self.assertEqual(matches, {})
            self.assertEqual(len(unmatched), 1)
            self.assertTrue(original.exists())


if __name__ == "__main__":
    unittest.main()
