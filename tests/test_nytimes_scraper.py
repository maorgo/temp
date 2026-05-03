import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from aggregator.models import Article
from aggregator.nytimes_scraper import fetch, _clean_reader_output


def _make_entry(
    title="Breaking News",
    link="https://nytimes.com/article/1",
    summary="Article summary text",
    published_parsed=(2026, 5, 3, 12, 0, 0, 5, 123, 0),
):
    entry = MagicMock()
    data = {
        "title": title,
        "link": link,
        "summary": summary,
        "published_parsed": published_parsed,
    }
    entry.get.side_effect = lambda k, default="": data.get(k, default)
    entry.title = title
    entry.link = link
    entry.summary = summary
    entry.published_parsed = published_parsed
    return entry


def _make_feed(entries=None, bozo=False):
    feed = MagicMock()
    feed.entries = entries if entries is not None else []
    feed.bozo = bozo
    feed.bozo_exception = Exception("feed parse error")
    return feed


def _mock_jina_response(text: str = "", status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


class TestCleanReaderOutput(unittest.TestCase):

    def test_strips_before_markdown_content_marker(self):
        text = "Preamble junk\nMarkdown Content:\nActual content here"
        self.assertEqual(_clean_reader_output(text), "Actual content here")

    def test_no_marker_returns_full_text_stripped(self):
        self.assertEqual(_clean_reader_output("  some text  "), "some text")

    def test_removes_skip_advertisement_links(self):
        text = "Paragraph one\n[SKIP ADVERTISEMENT](https://example.com)\nParagraph two"
        result = _clean_reader_output(text)
        self.assertNotIn("SKIP ADVERTISEMENT", result)
        self.assertIn("Paragraph one", result)
        self.assertIn("Paragraph two", result)

    def test_strips_leading_advertisement_lines(self):
        text = "Advertisement\nReal content"
        self.assertEqual(_clean_reader_output(text), "Real content")

    def test_strips_leading_blank_lines(self):
        text = "\n\nReal content"
        self.assertEqual(_clean_reader_output(text), "Real content")

    def test_empty_string_returns_empty(self):
        self.assertEqual(_clean_reader_output(""), "")

    def test_marker_and_advertisement_combined(self):
        text = "Junk\nMarkdown Content:\nAdvertisement\n[SKIP ADVERTISEMENT](x)\nBody text"
        result = _clean_reader_output(text)
        self.assertEqual(result, "Body text")


class TestNYTimesFetch(unittest.TestCase):

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_returns_list_of_articles(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry()])
        mock_get.return_value = _mock_jina_response()
        result = fetch()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Article)

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_maps_all_fields_correctly(self, mock_parse, mock_get):
        entry = _make_entry(title="Big Story", link="https://nytimes.com/big", summary="Key details")
        mock_parse.return_value = _make_feed([entry])
        mock_get.return_value = _mock_jina_response(text="")
        article = fetch()[0]
        self.assertEqual(article.title, "Big Story")
        self.assertEqual(article.url, "https://nytimes.com/big")
        self.assertEqual(article.full_article, "Key details")
        self.assertEqual(article.source, "NYTimes")

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_source_is_always_nytimes(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(), _make_entry(title="Other", link="https://nytimes.com/2")])
        mock_get.return_value = _mock_jina_response()
        for article in fetch():
            self.assertEqual(article.source, "NYTimes")

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_skips_entry_with_missing_title(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry(title=""), _make_entry(title="Valid")])
        with patch("aggregator.nytimes_scraper.requests.get", return_value=_mock_jina_response()):
            result = fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Valid")

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_skips_entry_with_missing_link(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry(link=""), _make_entry()])
        with patch("aggregator.nytimes_scraper.requests.get", return_value=_mock_jina_response()):
            result = fetch()
        self.assertEqual(len(result), 1)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_raises_runtime_error_on_bozo_feed_with_no_entries(self, mock_parse):
        mock_parse.return_value = _make_feed(entries=[], bozo=True)
        with self.assertRaises(RuntimeError):
            fetch()

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_bozo_feed_with_entries_does_not_raise(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed(entries=[_make_entry()], bozo=True)
        mock_get.return_value = _mock_jina_response()
        self.assertEqual(len(fetch()), 1)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_empty_feed_returns_empty_list(self, mock_parse):
        mock_parse.return_value = _make_feed(entries=[])
        self.assertEqual(fetch(), [])

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_parses_published_date_from_struct_time(self, mock_parse, mock_get):
        entry = _make_entry(published_parsed=(2026, 5, 3, 14, 30, 0, 5, 123, 0))
        mock_parse.return_value = _make_feed([entry])
        mock_get.return_value = _mock_jina_response()
        self.assertEqual(fetch()[0].published, datetime(2026, 5, 3, 14, 30, 0, tzinfo=timezone.utc))

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_fallback_date_when_published_parsed_is_none(self, mock_parse, mock_get):
        entry = _make_entry(published_parsed=None)
        mock_parse.return_value = _make_feed([entry])
        mock_get.return_value = _mock_jina_response()
        before = datetime.now(tz=timezone.utc)
        article = fetch()[0]
        after = datetime.now(tz=timezone.utc)
        self.assertGreaterEqual(article.published, before)
        self.assertLessEqual(article.published, after)

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_returns_all_entries_from_feed(self, mock_parse, mock_get):
        entries = [_make_entry(title=f"Story {i}", link=f"https://nytimes.com/{i}") for i in range(5)]
        mock_parse.return_value = _make_feed(entries)
        mock_get.return_value = _mock_jina_response()
        self.assertEqual(len(fetch()), 5)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_calls_nytimes_rss_url(self, mock_parse):
        mock_parse.return_value = _make_feed([])
        fetch()
        url = mock_parse.call_args[0][0]
        self.assertIn("nytimes.com", url)
        self.assertIn("rss", url)

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_jina_body_used_when_returned(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(summary="RSS fallback")])
        mock_get.return_value = _mock_jina_response(text="Full article body from Jina")
        self.assertEqual(fetch()[0].full_article, "Full article body from Jina")

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_falls_back_to_rss_summary_when_jina_returns_empty(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(summary="RSS fallback")])
        mock_get.return_value = _mock_jina_response(text="")
        self.assertEqual(fetch()[0].full_article, "RSS fallback")

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_falls_back_to_rss_on_request_error(self, mock_parse, mock_get):
        import requests as req_module
        mock_parse.return_value = _make_feed([_make_entry(summary="RSS only")])
        mock_get.side_effect = req_module.RequestException("timeout")
        self.assertEqual(fetch()[0].full_article, "RSS only")

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_one_failed_url_does_not_fail_run(self, mock_parse, mock_get):
        import requests as req_module
        entries = [_make_entry(title=f"Story {i}", link=f"https://nytimes.com/{i}") for i in range(3)]
        mock_parse.return_value = _make_feed(entries)
        mock_get.side_effect = [
            req_module.RequestException("fail"),
            _mock_jina_response(text="Body 1"),
            _mock_jina_response(text="Body 2"),
        ]
        result = fetch()
        self.assertEqual(len(result), 3)

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_jina_request_uses_correct_headers(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(link="https://nytimes.com/story")])
        mock_get.return_value = _mock_jina_response()
        fetch()
        call_kwargs = mock_get.call_args
        headers = call_kwargs[1]["headers"]
        self.assertIn("ContentAggregator", headers["User-Agent"])
        self.assertEqual(headers["Accept"], "text/plain")

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_jina_request_uses_correct_url(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(link="https://nytimes.com/story")])
        mock_get.return_value = _mock_jina_response()
        fetch()
        called_url = mock_get.call_args[0][0]
        self.assertIn("r.jina.ai", called_url)
        self.assertIn("nytimes.com/story", called_url)

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_preserves_input_order(self, mock_parse, mock_get):
        entries = [_make_entry(title=f"Story {i}", link=f"https://nytimes.com/{i}") for i in range(5)]
        mock_parse.return_value = _make_feed(entries)
        mock_get.return_value = _mock_jina_response()
        result = fetch()
        self.assertEqual([a.title for a in result], [f"Story {i}" for i in range(5)])

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_empty_summary_stored_as_empty_string(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(summary="")])
        mock_get.return_value = _mock_jina_response(text="")
        self.assertEqual(fetch()[0].full_article, "")


if __name__ == "__main__":
    unittest.main()
