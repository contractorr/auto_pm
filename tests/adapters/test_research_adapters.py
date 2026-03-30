from datetime import UTC

from pm_agent.adapters.research import ArxivResearchClient, CompetitorResearchClient


class FakeCompetitorClient(CompetitorResearchClient):
    def fetch_page_summary(self, url: str):
        return super().fetch_page_summary(url)


def test_competitor_parser_extracts_title_and_description(monkeypatch):
    html = """
    <html>
      <head>
        <title>Example AI Product</title>
        <meta name="description" content="Automation for onboarding and workflows." />
      </head>
      <body><h1>Example</h1><p>Automation for onboarding teams.</p></body>
    </html>
    """

    class FakeResponse:
        status = 200

        def read(self):
            return html.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "pm_agent.adapters.research.urlopen",
        lambda request, timeout=20: FakeResponse(),
    )
    summary = CompetitorResearchClient().fetch_page_summary("https://example.com")
    assert summary.title == "Example AI Product"
    assert "Automation for onboarding" in summary.description


def test_arxiv_parser_extracts_entries(monkeypatch):
    xml = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2501.12345v1</id>
        <published>2026-03-01T12:00:00Z</published>
        <title>Agentic onboarding systems</title>
        <summary>How onboarding and workflows can be improved.</summary>
      </entry>
    </feed>
    """

    class FakeResponse:
        status = 200

        def read(self):
            return xml.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "pm_agent.adapters.research.urlopen",
        lambda request, timeout=20: FakeResponse(),
    )
    entries = ArxivResearchClient().fetch_category_entries("cs.HC")
    assert len(entries) == 1
    assert entries[0].arxiv_id == "2501.12345v1"
    assert entries[0].published_at.tzinfo == UTC
