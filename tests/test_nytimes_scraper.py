import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from aggregator.models import Article
from aggregator.nytimes_scraper import fetch


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


def _api_response(abstract="Abstract text.", lead_paragraph="Lead paragraph text."):
    return {"response": {"docs": [{"abstract": abstract, "lead_paragraph": lead_paragraph}]}}


class TestNYTimesFetch(unittest.TestCase):

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_returns_list_of_articles(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry()])
        result = fetch()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Article)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_maps_all_fields_correctly(self, mock_parse):
        entry = _make_entry(title="Big Story", link="https://nytimes.com/big", summary="Key details")
        mock_parse.return_value = _make_feed([entry])

        article = fetch()[0]
        self.assertEqual(article.title, "Big Story")
        self.assertEqual(article.url, "https://nytimes.com/big")
        self.assertEqual(article.full_article, "Key details")
        self.assertEqual(article.source, "NYTimes")

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_source_is_always_nytimes(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry(), _make_entry(title="Other", link="https://nytimes.com/2")])
        for article in fetch():
            self.assertEqual(article.source, "NYTimes")

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_skips_entry_with_missing_title(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry(title=""), _make_entry(title="Valid")])
        result = fetch()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Valid")

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_skips_entry_with_missing_link(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry(link=""), _make_entry()])
        result = fetch()
        self.assertEqual(len(result), 1)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_raises_runtime_error_on_bozo_feed_with_no_entries(self, mock_parse):
        mock_parse.return_value = _make_feed(entries=[], bozo=True)
        with self.assertRaises(RuntimeError):
            fetch()

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_bozo_feed_with_entries_does_not_raise(self, mock_parse):
        mock_parse.return_value = _make_feed(entries=[_make_entry()], bozo=True)
        result = fetch()
        self.assertEqual(len(result), 1)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_empty_feed_returns_empty_list(self, mock_parse):
        mock_parse.return_value = _make_feed(entries=[])
        self.assertEqual(fetch(), [])

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_parses_published_date_from_struct_time(self, mock_parse):
        entry = _make_entry(published_parsed=(2026, 5, 3, 14, 30, 0, 5, 123, 0))
        mock_parse.return_value = _make_feed([entry])
        article = fetch()[0]
        self.assertEqual(article.published, datetime(2026, 5, 3, 14, 30, 0, tzinfo=timezone.utc))

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_fallback_date_when_published_parsed_is_none(self, mock_parse):
        entry = _make_entry(published_parsed=None)
        mock_parse.return_value = _make_feed([entry])
        before = datetime.now(tz=timezone.utc)
        article = fetch()[0]
        after = datetime.now(tz=timezone.utc)
        self.assertGreaterEqual(article.published, before)
        self.assertLessEqual(article.published, after)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_returns_all_entries_from_feed(self, mock_parse):
        entries = [_make_entry(title=f"Story {i}", link=f"https://nytimes.com/{i}") for i in range(5)]
        mock_parse.return_value = _make_feed(entries)
        self.assertEqual(len(fetch()), 5)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_calls_nytimes_rss_url(self, mock_parse):
        mock_parse.return_value = _make_feed([])
        fetch()
        url = mock_parse.call_args[0][0]
        self.assertIn("nytimes.com", url)
        self.assertIn("rss", url)

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_empty_summary_stored_as_empty_string(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry(summary="")])
        self.assertEqual(fetch()[0].full_article, "")

    # --- API integration tests ---

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_uses_api_when_key_provided(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry()])
        mock_get.return_value.json.return_value = _api_response("Abstract.", "Lead paragraph.")
        mock_get.return_value.raise_for_status = MagicMock()

        article = fetch(api_key="test-key")[0]
        self.assertEqual(article.full_article, "Abstract.\n\nLead paragraph.")

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_falls_back_to_rss_summary_when_api_returns_no_docs(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(summary="RSS fallback")])
        mock_get.return_value.json.return_value = {"response": {"docs": []}}
        mock_get.return_value.raise_for_status = MagicMock()

        article = fetch(api_key="test-key")[0]
        self.assertEqual(article.full_article, "RSS fallback")

    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_skips_api_when_no_key(self, mock_parse):
        mock_parse.return_value = _make_feed([_make_entry(summary="RSS only")])
        # No api_key passed and NYT_API_KEY not in env — should use RSS summary directly
        with patch("aggregator.nytimes_scraper.os.getenv", return_value=""):
            article = fetch()[0]
        self.assertEqual(article.full_article, "RSS only")

    @patch("aggregator.nytimes_scraper.requests.get")
    @patch("aggregator.nytimes_scraper.feedparser.parse")
    def test_api_sends_correct_params(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(link="https://nytimes.com/article/1")])
        mock_get.return_value.json.return_value = _api_response()
        mock_get.return_value.raise_for_status = MagicMock()

        fetch(api_key="my-key")
        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"]
        self.assertIn("my-key", params["api-key"])
        self.assertIn("abstract", params["fl"])
        self.assertIn("lead_paragraph", params["fl"])


if __name__ == "__main__":
    unittest.main()
