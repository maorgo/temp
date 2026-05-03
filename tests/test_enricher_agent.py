import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from aggregator.models import Article, SynthesizedContent
from Agents.enricher_agent import enrich, _parse_extra_facts


def _make_article(title="Test Article"):
    return Article(
        title=title,
        url="https://example.com/1",
        source="NYTimes",
        published=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
        full_article="Some article content",
    )


def _make_synthesis(bullets=None):
    return SynthesizedContent(
        title="Test",
        bullets=bullets or ["Point 1", "Point 2", "Point 3"],
        conclusion="Conclusion sentence.",
    )


def _mock_subprocess(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.stdout = stdout
    result.returncode = 0
    return result


_VALID_RESPONSE = "EXTRA FACTS:\n- Fact one\n- Fact two\n- Fact three"


class TestParseExtraFacts(unittest.TestCase):

    def test_extracts_facts_from_extra_facts_section(self):
        self.assertEqual(_parse_extra_facts("EXTRA FACTS:\n- Fact one\n- Fact two\n- Fact three"),
                         ["Fact one", "Fact two", "Fact three"])

    def test_extracts_two_facts(self):
        self.assertEqual(_parse_extra_facts("EXTRA FACTS:\n- Alpha\n- Beta"), ["Alpha", "Beta"])

    def test_limits_output_to_three_facts(self):
        text = "EXTRA FACTS:\n- F1\n- F2\n- F3\n- F4\n- F5"
        self.assertEqual(len(_parse_extra_facts(text)), 3)

    def test_returns_empty_list_when_section_missing(self):
        self.assertEqual(_parse_extra_facts("Some response without the expected header."), [])

    def test_returns_empty_list_on_empty_string(self):
        self.assertEqual(_parse_extra_facts(""), [])

    def test_strips_whitespace_from_each_fact(self):
        self.assertEqual(_parse_extra_facts("EXTRA FACTS:\n-  Padded fact  "), ["Padded fact"])

    def test_case_insensitive_section_header(self):
        self.assertEqual(_parse_extra_facts("extra facts:\n- Lowercase header fact"),
                         ["Lowercase header fact"])

    def test_ignores_lines_before_section(self):
        text = "Preamble text\n- Not a fact\nEXTRA FACTS:\n- Real fact"
        self.assertEqual(_parse_extra_facts(text), ["Real fact"])


class TestEnrich(unittest.TestCase):

    @patch("Agents.enricher_agent.subprocess.run")
    def test_returns_facts_from_subprocess(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        result = enrich(_make_article(), _make_synthesis())
        self.assertEqual(result, ["Fact one", "Fact two", "Fact three"])

    @patch("Agents.enricher_agent.subprocess.run", side_effect=subprocess.CalledProcessError(1, "claude"))
    def test_returns_empty_list_on_subprocess_error(self, _mock_run):
        result = enrich(_make_article(), _make_synthesis())
        self.assertEqual(result, [])

    @patch("Agents.enricher_agent.subprocess.run", side_effect=Exception("unexpected error"))
    def test_returns_empty_list_on_any_exception(self, _mock_run):
        result = enrich(_make_article(), _make_synthesis())
        self.assertEqual(result, [])

    @patch("Agents.enricher_agent.subprocess.run")
    def test_invokes_claude_cli(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        enrich(_make_article(), _make_synthesis())
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "claude")
        self.assertIn("-p", args)

    @patch("Agents.enricher_agent.subprocess.run")
    def test_mcp_config_includes_duckduckgo_server(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        enrich(_make_article(), _make_synthesis())
        args = mock_run.call_args[0][0]
        mcp_config = args[args.index("--mcp-config") + 1]
        config = __import__("json").loads(mcp_config)
        self.assertIn("duckduckgo", config["mcpServers"])

    @patch("Agents.enricher_agent.subprocess.run")
    def test_duckduckgo_server_requires_no_api_key(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        enrich(_make_article(), _make_synthesis())
        args = mock_run.call_args[0][0]
        mcp_config = args[args.index("--mcp-config") + 1]
        config = __import__("json").loads(mcp_config)
        self.assertNotIn("env", config["mcpServers"]["duckduckgo"])

    @patch("Agents.enricher_agent.subprocess.run")
    def test_uses_correct_model(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        enrich(_make_article(), _make_synthesis())
        args = mock_run.call_args[0][0]
        self.assertIn("--model", args)
        self.assertIn("claude-sonnet-4-6", args)

    @patch("Agents.enricher_agent.subprocess.run")
    def test_existing_bullets_included_in_prompt(self, mock_run):
        mock_run.return_value = _mock_subprocess(stdout=_VALID_RESPONSE)
        synthesis = _make_synthesis(bullets=["Bullet A", "Bullet B"])
        enrich(_make_article(), synthesis)
        args = mock_run.call_args[0][0]
        prompt = args[args.index("-p") + 1]
        self.assertIn("Bullet A", prompt)
        self.assertIn("Bullet B", prompt)


if __name__ == "__main__":
    unittest.main()
