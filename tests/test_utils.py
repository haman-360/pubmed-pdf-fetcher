from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from src.utils import extract_pmids, read_pmids


class ExtractPmidsTests(unittest.TestCase):
    def test_extracts_explicit_pmids_in_document_order(self) -> None:
        content = """
Published in 2026; pages 120-128.
PMID: 31452104
DOI: 10.1000/30049270
https://pubmed.ncbi.nlm.nih.gov/30049270/
31452104
# PMID: 99999999
"""

        self.assertEqual(extract_pmids(content), ["31452104", "30049270"])

    def test_ignores_unlabelled_numbers_inside_prose(self) -> None:
        self.assertEqual(extract_pmids("Year 2026 and sample size 12345678."), [])

    def test_reads_pmids_from_docx(self) -> None:
        document_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>PMID: 31452104</w:t></w:r></w:p>
  <w:p><w:r><w:t>30049270</w:t></w:r></w:p></w:body>
</w:document>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "abstracts.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", document_xml)

            self.assertEqual(read_pmids(path), ["31452104", "30049270"])


if __name__ == "__main__":
    unittest.main()
