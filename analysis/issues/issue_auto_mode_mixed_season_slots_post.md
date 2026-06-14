Follow-up evidence from broader live sweep.

Investigation method:
- interactive repo review and live CLI testing in Codex / GPT-5
- live Earth Engine-backed runs, then cache-backed reruns for confirmation
- helper report script added locally: `analysis/report_auto_season_alignment.py`

Test window:
- `2018-2020`
- `source=auto`

Transitional sweep summary:

| Site | Outcome | Notes |
|---|---|---|
| Nairobi | Guard triggered | counts `2018:1, 2019:2, 2020:1`; classic mixed-slot case |
| Kampala | No seasons | perhumid / alignment not informative |
| Addis Ababa | Stable 1-season/year | regrouping weak; regime changes across years |
| Niamey | Sparse seasons | only 2 season rows across 3 years |
| Bamako | Best exploratory case | `regime+onset_month` reused `0.667`, fragmentation `0.667` |
| Quito | Guard triggered | counts `2018:1, 2019:3, 2020:2`; severe fragmentation |
| Cajamarca | Guard triggered | counts `2018:2, 2019:1, 2020:1`; onset-month reuse better than regime key |

Takeaway:
- issue is real, but not universal
- humid/perhumid sites often produce no seasons, so alignment question does not apply there
- worst failures happen in transitional / bimodal / erratic regimes
- no single replacement key works across all tested regimes

Important detail from sweep:
- `regime+onset_month` helps in some places, but not enough for global auto-enable
- `Bamako` looked most promising
- `Quito` and `Cajamarca` showed that same idea can fragment badly

Current status in local testing:
- short-term guard now seems correct: if yearly season counts differ, skip season-slot LTM summary and warn
- fixed seasons still look like right path for comparison-grade multi-year seasonal LTMs
- longer-term regrouping, if attempted, likely needs region/regime-specific logic rather than one global alignment rule

Artifacts from sweep saved locally:
- `analysis/auto_season_alignment_report_transitional.md`
- `analysis/auto_season_alignment_report_transitional.json`
- `analysis/auto_season_alignment_report_transitional.csv`
