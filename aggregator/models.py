from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    title: str
    url: str
    source: str
    published: datetime
    full_article: str
    ai_summary: str = field(default="")


@dataclass
class SynthesizedContent:
    title: str
    bullets: list[str]
    conclusion: str
    extra_bullets: list[str] = field(default_factory=list)
