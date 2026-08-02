from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from src.pdf_finder import PdfFinder, PublisherPdfLinkParser


class FakeResponse:
    def __init__(self, chunks: list[bytes], content_type: str = "application/pdf") -> None:
        self.status_code = 200
        self.headers = {"Content-Type": content_type}
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        yield from self._chunks


class FailingResponse(FakeResponse):
    def iter_content(self, chunk_size: int):
        yield b"%PDF-1.7 partial"
        raise requests.ConnectionError("connection lost")


class PdfFinderTests(unittest.TestCase):
    def test_publisher_parser_finds_standard_pdf_metadata(self) -> None:
        parser = PublisherPdfLinkParser("https://journal.example.test/article/1")
        parser.feed('<meta name="citation_pdf_url" content="/article/1.pdf">')

        self.assertEqual(parser.pdf_url, "https://journal.example.test/article/1.pdf")

    def test_unpaywall_urls_are_deduplicated_in_priority_order(self) -> None:
        finder = PdfFinder()
        data = {
            "best_oa_location": {"url_for_pdf": "https://example.test/best.pdf"},
            "oa_locations": [
                {"url_for_pdf": "https://example.test/best.pdf"},
                {"url_for_pdf": "https://example.test/backup.pdf"},
            ],
        }

        self.assertEqual(
            finder._unpaywall_pdf_urls(data),
            ["https://example.test/best.pdf", "https://example.test/backup.pdf"],
        )

    def test_download_is_saved_atomically(self) -> None:
        finder = PdfFinder()
        finder.session.get = Mock(return_value=FakeResponse([b"%PDF-1.7\n", b"body"]))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "article.pdf"
            result = finder._download_if_pdf("https://example.test/article.pdf", destination, "test")

            self.assertTrue(result.success)
            self.assertTrue(finder.is_pdf_file(destination))
            self.assertFalse(destination.with_suffix(".pdf.part").exists())

    def test_interrupted_download_leaves_no_partial_pdf(self) -> None:
        finder = PdfFinder()
        finder.session.get = Mock(return_value=FailingResponse([]))
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "article.pdf"
            result = finder._download_if_pdf("https://example.test/article.pdf", destination, "test")

            self.assertFalse(result.success)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".pdf.part").exists())


if __name__ == "__main__":
    unittest.main()
