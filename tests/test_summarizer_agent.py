import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from aggregator.models import Article, SynthesizedContent
from Agents.summarizer_agent import _parse_response, synthesize, call_claude


def _make_article(title="Test Article", full_article="Some news content here"):
    return Article(
        title=title,
        url="https://example.com/1",
        source="NYTimes",
        published=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        full_article=full_article,
    )


def _mock_subprocess(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.stdout = stdout
    result.returncode = 0
    return result


_VALID_RESPONSE = "TITLE: Breaking News\nBULLETS:\n- Point one\n- Point two\n- Point three\nCONCLUSION: Key takeaway."


class TestParseResponse(unittest.TestCase):

    def test_extracts_title(self):
        result = _parse_response(_VALID_RESPONSE, "Fallback")
        self.assertEqual(result.title, "Breaking News")

    def test_extracts_all_bullets(self):
        result = _parse_response(_VALID_RESPONSE, "T")
        self.assertEqual(result.bullets, ["Point one", "Point two", "Point three"])

    def test_extracts_conclusion(self):
        result = _parse_response(_VALID_RESPONSE, "T")
        self.assertEqual(result.conclusion, "Key takeaway.")

    def test_falls_back_to_title_arg_when_title_missing(self):
        text = "BULLETS:\n- P1\nCONCLUSION: C"
        result = _parse_response(text, "Fallback Title")
        self.assertEqual(result.title, "Fallback Title")

    def test_handles_five_bullets(self):
        text = "TITLE: T\nBULLETS:\n- P1\n- P2\n- P3\n- P4\n- P5\nCONCLUSION: C"
        result = _parse_response(text, "T")
        self.assertEqual(len(result.bullets), 5)

    def test_handles_missing_conclusion(self):
        text = "TITLE: T\nBULLETS:\n- P1\n- P2"
        result = _parse_response(text, "T")
        self.assertEqual(result.conclusion, "")

    def test_handles_missing_bullets_section(self):
        text = "TITLE: T\nCONCLUSION: C"
        result = _parse_response(text, "T")
        self.assertEqual(result.bullets, [])

    def test_returns_synthesized_content_instance(self):
        result = _parse_response(_VALID_RESPONSE, "T")
        self.assertIsInstance(result, SynthesizedContent)

    def test_extra_bullets_defaults_to_empty(self):
        result = _parse_response(_VALID_RESPONSE, "T")
        self.assertEqual(result.extra_bullets, [])

    def test_strips_whitespace_from_bullets(self):
        text = "TITLE: T\nBULLETS:\n-  padded bullet  \nCONCLUSION: C"
        result = _parse_response(text, "T")
        self.assertEqual(result.bullets[0], "padded bullet")

    def test_ignores_lines_outside_bullets_section(self):
        text = "TITLE: T\nSome preamble\nBULLETS:\n- Only bullet\nCONCLUSION: C\nExtra line"
        result = _parse_response(text, "T")
        self.assertEqual(result.bullets, ["Only bullet"])


class TestCallClaude(unittest.TestCase):

    @patch("Agents.summarizer_agent.subprocess.run")
    def test_uses_correct_model(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        call_claude(_make_article())
        args = mock_run.call_args[0][0]
        self.assertIn("--model", args)
        self.assertIn("claude-sonnet-4-6", args)

    @patch("Agents.summarizer_agent.subprocess.run")
    def test_passes_system_prompt_flag(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        call_claude(_make_article())
        args = mock_run.call_args[0][0]
        self.assertIn("--system-prompt", args)

    @patch("Agents.summarizer_agent.subprocess.run")
    def test_user_message_contains_article_title_and_content(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        call_claude(_make_article(title="My Headline", full_article="The article body"))
        args = mock_run.call_args[0][0]
        prompt = args[args.index("-p") + 1]
        self.assertIn("My Headline", prompt)
        self.assertIn("The article body", prompt)

    @patch("Agents.summarizer_agent.subprocess.run")
    def test_returns_synthesized_content(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        result = call_claude(_make_article())
        self.assertIsInstance(result, SynthesizedContent)

    @patch("Agents.summarizer_agent.subprocess.run")
    def test_invokes_claude_cli(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        call_claude(_make_article())
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "claude")
        self.assertIn("-p", args)

    @patch("Agents.summarizer_agent.subprocess.run")
    def test_retries_on_called_process_error(self, mock_run):
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "claude"),
            _mock_subprocess(stdout=_VALID_RESPONSE),
        ]
        result = call_claude(_make_article())
        self.assertEqual(mock_run.call_count, 2)
        self.assertIsInstance(result, SynthesizedContent)

    def testcall_claude_has_tenacity_retry_decorator(self):
        self.assertTrue(hasattr(call_claude, "retry"))


class TestSynthesize(unittest.TestCase):

    @patch("Agents.enricher_agent.enrich", return_value=["Extra 1", "Extra 2"])
    @patch("Agents.summarizer_agent.subprocess.run")
    def test_returns_synthesized_content(self, mock_run, _mock_enrich):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        result = synthesize(_make_article())
        self.assertIsInstance(result, SynthesizedContent)

    @patch("Agents.enricher_agent.enrich", return_value=["Extra fact A", "Extra fact B"])
    @patch("Agents.summarizer_agent.subprocess.run")
    def test_extra_bullets_populated_from_enricher(self, mock_run, _mock_enrich):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        result = synthesize(_make_article())
        self.assertEqual(result.extra_bullets, ["Extra fact A", "Extra fact B"])

    @patch("Agents.enricher_agent.enrich", return_value=[])
    @patch("Agents.summarizer_agent.subprocess.run")
    def test_enrich_called_with_original_article_and_synthesis(self, mock_run, mock_enrich):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        article = _make_article()
        synthesize(article)
        mock_enrich.assert_called_once()
        call_article, call_synthesis = mock_enrich.call_args[0]
        self.assertIs(call_article, article)
        self.assertIsInstance(call_synthesis, SynthesizedContent)

    @patch("Agents.enricher_agent.enrich", return_value=[])
    @patch("Agents.summarizer_agent.subprocess.run")
    def test_synthesis_bullets_present_before_enrichment(self, mock_run, mock_enrich):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        synthesize(_make_article())
        _, synthesis_passed = mock_enrich.call_args[0]
        self.assertGreater(len(synthesis_passed.bullets), 0)


if __name__ == "__main__":
    unittest.main()
