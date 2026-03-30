from pathlib import Path

from pm_agent.repo.product import load_product_context


def test_load_product_context_parses_expected_sections(tmp_path: Path):
    product_file = tmp_path / "PRODUCT.md"
    product_file.write_text(
        "\n".join(
            [
                "# Product Vision",
                "",
                "Build a focused AI product.",
                "",
                "## Target Users",
                "- solo builders",
                "- operators",
                "",
                "## Non-Goals",
                "- social networking",
                "",
                "## Current Strategic Priority",
                "Improve onboarding clarity.",
            ]
        ),
        encoding="utf-8",
    )

    product = load_product_context(product_file)

    assert product.vision == "Build a focused AI product."
    assert product.target_users == ["solo builders", "operators"]
    assert product.non_goals == ["social networking"]
    assert product.strategic_priorities == ["Improve onboarding clarity."]


def test_load_product_context_returns_empty_context_when_missing(tmp_path: Path):
    product = load_product_context(tmp_path / "PRODUCT.md")
    assert product.vision == ""
    assert product.target_users == []
