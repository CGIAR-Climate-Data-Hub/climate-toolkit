"""Translation coverage and freshness for the MkDocs site and landing READMEs."""

import hashlib
import re
from pathlib import Path

import pytest
import yaml

import climate_toolkit as ct


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("fr", "es")
# Existing pages still using MkDocs' English fallback. Remove an entry when
# both translations land. A new page requires translations or an explicit entry.
ENGLISH_ONLY = {
    "docs/api/analysis.md",
    "docs/api/comparison.md",
    "docs/api/fetching.md",
    "docs/datasets.md",
    "docs/direct_cloud_access.md",
    "docs/distribution_workflow.md",
    "docs/example_workflow.md",
    "docs/human_heat_workflow.md",
    "docs/outputs_by_module.md",
    "docs/thi_workflow.md",
    "docs/use-as-a-package.md",
    "docs/weather_station_workflows.md",
}
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def test_translation_inventory():
    english_pages = {p for p in PAGES if not p.stem.endswith((".fr", ".es"))}
    for page in ENGLISH_ONLY:
        assert ROOT / page in english_pages, f"Remove obsolete English fallback: {page}"

    for page in PAGES:
        if page.stem.endswith((".fr", ".es")):
            assert page.with_suffix("").with_suffix(".md") in english_pages, page


@pytest.mark.parametrize("lang", LANGUAGES)
def test_translation_sources(lang):
    errors = []
    for source in PAGES:
        if source.stem.endswith((".fr", ".es")):
            continue
        relative = source.relative_to(ROOT).as_posix()
        translation = source.with_suffix(f".{lang}.md")
        if relative in ENGLISH_ONLY and not translation.exists():
            continue
        if not translation.is_file():
            errors.append(f"Missing {translation.relative_to(ROOT)} for {relative}")
            continue
        english = source.read_text(encoding="utf-8")
        digest = hashlib.sha256(english.encode("utf-8")).hexdigest()
        marker = f"<!-- source-sha256: {digest} -->"
        content = translation.read_text(encoding="utf-8")
        markers = re.findall(r"^<!-- source-sha256: .*? -->$", content, re.MULTILINE)
        if markers != [marker]:
            errors.append(
                f"Review {translation.relative_to(ROOT)} against {relative}, then record {marker}"
            )
        # A previous translation dropped an Earth Engine billing advisory even
        # though its link and setup examples still passed the rendered-site checks.
        if source.parent != ROOT:
            admonition = r"^!!! (\w+)"
            if re.findall(admonition, english, re.MULTILINE) != re.findall(
                admonition, content, re.MULTILINE
            ):
                errors.append(
                    f"Check missing or changed advisories in {translation.relative_to(ROOT)}"
                )
        if relative in ENGLISH_ONLY:
            errors.append(
                f"Finish translations of {relative} and remove its English fallback entry"
            )
    assert not errors, "\n" + "\n".join(errors)


def nav_labels(entries):
    for entry in entries:
        for label, target in entry.items():
            yield label
            if isinstance(target, list):
                yield from nav_labels(target)


def test_navigation_translations():
    # BaseLoader reads the tagged MkDocs config without importing the docs plugins.
    config = yaml.load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    i18n = next(p["i18n"] for p in config["plugins"] if isinstance(p, dict) and "i18n" in p)
    locales = {item["locale"]: item for item in i18n["languages"]}
    labels = set(nav_labels(config["nav"]))
    for lang in LANGUAGES:
        translated = locales[lang]["nav_translations"]
        assert translated.keys() == labels, (
            f"{lang} navigation differs: {labels ^ translated.keys()}"
        )
        assert all(label.strip() for label in translated.values())


@pytest.mark.parametrize("suffix", ["", ".fr", ".es"])
def test_api_overview_lists_public_callables(suffix):
    overview = (ROOT / f"docs/api/index{suffix}.md").read_text(encoding="utf-8")
    names = re.findall(r"^\| `ct\.(\w+)` \|", overview, re.MULTILINE)
    assert sorted(names) == sorted(name for name in ct.__all__ if callable(getattr(ct, name)))
