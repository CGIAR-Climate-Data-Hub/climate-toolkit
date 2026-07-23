# Docs: About/comms landing page, EN/FR/ES language toggle, and community entry points — extend to `use-as-a-package` and README

## Summary

Branch `docs/about-community-i18n` adds a non-technical **About** landing page
(problem / solution / who it's for / vision / get involved) in **English,
French, and Spanish**, with a Material language selector via
`mkdocs-static-i18n` (suffix structure: `about.md`, `about.fr.md`,
`about.es.md`; untranslated pages fall back to English). It also positions the
About page as the future home for **training-course materials** and
instructions for **feedback, feature requests, and getting involved**
(GitHub Issues + Discussions).

This issue is to decide how the rest of the user-facing surface should handle
the same concerns.

## Questions to resolve

1. **`use-as-a-package.md` (and `getting_started.md`)** — do we translate
   these into FR/ES too? They are long and change often, so options are:
   a. full manual translation (high maintenance);
   b. translate only a short "orientation" intro block per page, leave
      reference content in English (recommended to start);
   c. leave them English-only and rely on fallback (current state after this
      branch).
   Proposal: (b) for `getting_started.md` since trainees will land there;
   (c) for the API/reference pages.

2. **Package README** — currently long (~50 KB) and mixes audiences. Proposal:
   - move comms/dissemination framing to the site About page (done on the
     branch) and keep the README technical;
   - add a short "About & community" section near the top linking to the
     About page (EN/FR/ES anchors), Issues, and Discussions;
   - consider trimming README content that duplicates the docs site, per the
     single-source-of-truth principle in AGENTS.md.

3. **GitHub Discussions** — enable Discussions on the repo (Settings →
   Features) with categories: Announcements, Q&A / Support, Ideas & feature
   requests, Show and tell, Training course. Seed with a welcome post that
   mirrors the About page's "Get involved" section. Link Discussions from the
   About page (already done), README, and issue templates.

4. **Training materials home** — course notebooks/videos will be hosted under
   the docs site (e.g. `docs/training/`), also i18n'd. Placeholder card exists
   on the About page; structure TBD with the course build (Wanjiku/Michel).

5. **Translation maintenance** — agree a light process: English is
   authoritative; FR/ES updated per release (not per commit); LLM-assisted
   first pass, human review by ES (Andes team / Magalí) and FR (WA/AIMS
   contacts) speakers, per the approach already used for the Blueprint's
   Spanish piloting.

## Done on branch `docs/about-community-i18n`

- `docs/about.md`, `docs/about.fr.md`, `docs/about.es.md` (grid-card layout)
- `mkdocs.yml`: `i18n` plugin config, language selector, `attr_list`,
  `md_in_html`, `pymdownx.emoji` extensions, About nav entry (+ FR/ES nav
  translations)
- `pyproject.toml`: `mkdocs-static-i18n` added to the `docs` group

## Out of scope

- Translating the API reference (mkdocstrings output)
- CLI help text localisation
