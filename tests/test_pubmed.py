from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.pubmed import PubMedClient


def pubmed_response(pmid: str) -> Mock:
    response = Mock()
    response.content = f"""<PubmedArticleSet><PubmedArticle><MedlineCitation>
      <PMID>{pmid}</PMID><Article><ArticleTitle>Article {pmid}</ArticleTitle></Article>
    </MedlineCitation></PubmedArticle></PubmedArticleSet>""".encode()
    return response


class PubMedClientTests(unittest.TestCase):
    @patch("src.pubmed.time.sleep")
    def test_batches_large_requests_and_preserves_input_order(self, sleep: Mock) -> None:
        client = PubMedClient()
        client.session = Mock()
        client.session.post.return_value = pubmed_response("1")
        client.session.get.return_value = pubmed_response("201")
        pmids = [str(value) for value in range(1, 202)]

        articles = client.fetch_metadata(pmids)

        self.assertEqual([article.pmid for article in articles], pmids)
        client.session.post.assert_called_once()
        client.session.get.assert_called_once()
        sleep.assert_called_once_with(0.34)


if __name__ == "__main__":
    unittest.main()
