import unittest
from datetime import datetime, timezone

from aggregator.models import Article, SynthesizedContent


class TestArticle(unittest.TestCase):

    def _make(self, **kwargs):
        defaults = dict(
            title="Test Article",
            url="https://example.com/1",
            source="NYTimes",
            published=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
            full_article="Raw summary text",
        )
        return Article(**{**defaults, **kwargs})

    def test_all_required_fields_stored(self):
        a = self._make()
        self.assertEqual(a.title, "Test Article")
        self.assertEqual(a.url, "https://example.com/1")
        self.assertEqual(a.source, "NYTimes")
        self.assertIsInstance(a.published, datetime)
        self.assertEqual(a.full_article, "Raw summary text")

    def test_ai_summary_defaults_to_empty_string(self):
        self.assertEqual(self._make().ai_summary, "")

    def test_ai_summary_can_be_set_at_construction(self):
        a = self._make()
        a.ai_summary = "Generated summary"
        self.assertEqual(a.ai_summary, "Generated summary")

    def test_published_timezone_preserved(self):
        dt = datetime(2026, 5, 3, 14, 30, tzinfo=timezone.utc)
        a = self._make(published=dt)
        self.assertEqual(a.published.tzinfo, timezone.utc)


class TestSynthesizedContent(unittest.TestCase):

    def _make(self, **kwargs):
        defaults = dict(title="Title", bullets=["P1", "P2"], conclusion="Conclusion")
        return SynthesizedContent(**{**defaults, **kwargs})

    def test_all_required_fields_stored(self):
        s = self._make()
        self.assertEqual(s.title, "Title")
        self.assertEqual(s.bullets, ["P1", "P2"])
        self.assertEqual(s.conclusion, "Conclusion")

    def test_extra_bullets_defaults_to_empty_list(self):
        self.assertEqual(self._make().extra_bullets, [])

    def test_extra_bullets_can_be_set(self):
        s = self._make()
        s.extra_bullets = ["Extra 1", "Extra 2"]
        self.assertEqual(s.extra_bullets, ["Extra 1", "Extra 2"])

    def test_extra_bullets_not_shared_between_instances(self):
        s1 = self._make()
        s2 = self._make()
        s1.extra_bullets.append("only in s1")
        self.assertEqual(s2.extra_bullets, [])

    def test_bullets_accepts_up_to_five_items(self):
        s = self._make(bullets=["P1", "P2", "P3", "P4", "P5"])
        self.assertEqual(len(s.bullets), 5)


if __name__ == "__main__":
    unittest.main()
