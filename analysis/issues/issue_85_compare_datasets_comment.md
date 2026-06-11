Additional module-level consequence of this root issue:

`climate_tookit/compare_datasets/compare_datasets.py` currently says its outputs are `"not synthetic mock data"`, but when `nex_gddp` is included it still routes through the active placeholder `nex_gddp` backend via `preprocess_data(...)`.

So `compare_datasets` can currently present NEX-GDDP comparison series as analysis-ready non-synthetic output even though the underlying NEX path is still synthetic.

This seems better treated as a user-facing symptom of `#85` than as a separate backend issue.
