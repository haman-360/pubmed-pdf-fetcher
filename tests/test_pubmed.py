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


def linkout_response(pmid: str, url: str) -> Mock:
    response = Mock()
    response.content = f"""<eLinkResult><LinkSet><IdUrlList><IdUrlSet>
      <Id>{pmid}</Id><ObjUrl><Url>{url}</Url><Category>Full Text Sources</Category>
      <Attribute>free resource</Attribute></ObjUrl>
    </IdUrlSet></IdUrlList></LinkSet></eLinkResult>""".encode()
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
        requested_urls = [call.args[0] for call in client.session.get.call_args_list]
        self.assertEqual(sum(url.endswith("/efetch.fcgi") for url in requested_urls), 1)
        self.assertEqual(sum(url.endswith("/elink.fcgi") for url in requested_urls), 2)
        sleep.assert_called_once_with(0.34)

    def test_fetches_pubmed_free_full_text_link(self) -> None:
        client = PubMedClient()
        client.session = Mock()
        client.session.get.side_effect = [
            pubmed_response("42526949"),
            linkout_response("42526949", "https://www.bmj.com/free-article"),
        ]

        articles = client.fetch_metadata(["42526949"])

        self.assertEqual(articles[0].free_full_text_url, "https://www.bmj.com/free-article")


if __name__ == "__main__":
    unittest.main()
