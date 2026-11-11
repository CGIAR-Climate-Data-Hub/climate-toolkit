# Summary

Briefly describe what this pull request changes.

# Problem / Motivation

What problem does this solve, or what capability does it add?

# Scope

- In scope:
- Out of scope:

# Implementation Notes

List the important technical choices, assumptions, trade-offs, or follow-up items.

# Data / Access / Runtime Notes

Note any dataset constraints, authentication needs, cache behavior, long-running steps, or external services touched by this PR.

# Testing

- Tests added/updated:
- Commands run:
- Manual checks:
- Not tested:

# Reviewer Guidance

Call out the highest-risk files, behaviors, or assumptions that deserve focused review.

# Related Issues

Link issues, discussions, or follow-up tickets.

# Checklist

- [ ] I reviewed my own diff for unrelated changes.
- [ ] I used a dedicated branch for this work.
- [ ] I added or updated tests where needed.
- [ ] I documented any auth, data, cache, or runtime implications.
- [ ] I included reviewer test steps or validation notes.
- [ ] I linked the relevant issue(s).
- [ ] For English documentation changes, I compared the affected French and Spanish pages with the revised source, updated their wording where needed, and refreshed their `source-sha256` comments. The translated READMEs summarize the English README, so some changes only require refreshing the comments. Run `uv run pytest tests/test_doc_translations.py` for the affected filenames and expected hashes. Add French and Spanish versions alongside every new English documentation page. For new or revised translations, identify the language reviewers in Reviewer Guidance.
