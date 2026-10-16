"""B5: the article's Cedar snippet is a copy of the deployed forbid, never typed."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOYED = ROOT / "evidence/2026-10-16/d1/forbid-deployed-redacted.cedar"
ARTICLE = ROOT / "docs/article-draft.md"


def article_forbid_block() -> str:
    lines = ARTICLE.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("```") and i + 1 < len(lines) and lines[i + 1].startswith("forbid("):
            end = next(j for j in range(i + 1, len(lines)) if lines[j].strip().startswith("```"))
            return "\n".join(lines[i + 1:end])
    raise AssertionError("no forbid code block in the article")


def test_article_snippet_is_the_deployed_forbid():
    assert article_forbid_block() == DEPLOYED.read_text().rstrip("\n")


def test_action_name_uses_three_underscores():
    assert 'AgentCore::Action::"ReviewerTools___record_adverse_determination"' in article_forbid_block()
