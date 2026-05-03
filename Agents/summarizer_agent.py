import subprocess

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from aggregator.models import Article, SynthesizedContent

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are an objective news content synthesis agent.

Your task is to analyze a news article and produce a structured summary.

Rules:
- Be strictly factual and objective. Do not editorialize or express opinions.
- Extract only information that appears in the provided content.
- Respond in the same language as the input content (English for English articles, Hebrew for Hebrew articles).

Output format — respond with exactly this structure, replacing the placeholders:

TITLE: <the article title, unchanged>
BULLETS:
- <key point 1>
- <key point 2>
- <key point 3>
- <key point 4 if warranted>
- <key point 5 if warranted>
CONCLUSION: <one sentence summarizing the overall significance or takeaway>

Produce 3 to 5 bullet points depending on how much distinct information the content contains. Each bullet must capture a separate fact or development."""


def synthesize(article: Article) -> SynthesizedContent:
    synthesis = call_claude(article)

    from Agents.enricher_agent import enrich
    synthesis.extra_bullets = enrich(article, synthesis)

    return synthesis


@retry(
    retry=retry_if_exception_type(subprocess.CalledProcessError),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def call_claude(article: Article) -> SynthesizedContent:
    user_message = f"Title: {article.title}\n\nContent: {article.full_article}"

    result = subprocess.run(
        [
            "claude", "-p", user_message,
            "--model", _MODEL,
            "--system-prompt", _SYSTEM_PROMPT,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return _parse_response(result.stdout.strip(), article.title)


def _parse_response(text: str, fallback_title: str) -> SynthesizedContent:
    title = fallback_title
    bullets: list[str] = []
    conclusion = ""

    lines = text.strip().splitlines()
    mode = None

    for line in lines:
        line = line.strip()
        if line.startswith("TITLE:"):
            title = line.removeprefix("TITLE:").strip()
        elif line == "BULLETS:":
            mode = "bullets"
        elif line.startswith("CONCLUSION:"):
            mode = None
            conclusion = line.removeprefix("CONCLUSION:").strip()
        elif mode == "bullets" and line.startswith("-"):
            bullets.append(line.removeprefix("-").strip())

    return SynthesizedContent(title=title, bullets=bullets, conclusion=conclusion)
