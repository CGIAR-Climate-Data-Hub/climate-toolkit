"""Task-local provider policy, also usable around higher-level workflows."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class BackendPolicy:
    backend: str = "auto"
    allow_gee: bool = True


_POLICY = ContextVar("climate_toolkit_backend_policy", default=None)
BACKENDS = ("auto", "huggingface", "dynamical", "gee")
DIRECT_SOURCES = {"chirps_v3_daily_rnl", "chirts_era5"}
GEE_SOURCES = {
    "agera_5",
    "era_5",
    "chirps_v2",
    "chirps_v3_daily_rnl",
    "chirts",
    "terraclimate",
    "imerg",
    "nex_gddp",
    "cmip_6",
    "soil_grid",
    "hwsd",
}


def resolve_policy(backend=None, allow_gee=None):
    current = _POLICY.get() or BackendPolicy(
        os.getenv("CLIMATE_TOOLKIT_BACKEND", "auto"),
        os.getenv("CLIMATE_TOOLKIT_ALLOW_GEE", "true").lower() not in {"0", "false", "no"},
    )
    resolved = BackendPolicy(
        current.backend if backend is None else backend,
        current.allow_gee if allow_gee is None else allow_gee,
    )
    if resolved.backend not in BACKENDS:
        raise ValueError(f"Unknown backend {resolved.backend!r}; choose {', '.join(BACKENDS)}")
    if resolved.backend == "gee" and not resolved.allow_gee:
        raise ValueError("backend='gee' conflicts with allow_gee=False")
    return resolved


@contextmanager
def backend_policy(*, backend=None, allow_gee=None):
    """Apply provider controls to all fetches within a workflow.

    Explicit provider selection affects datasets with direct adapters. Other
    datasets keep their existing routes, subject to the global GEE prohibition.
    Contexts nest safely and do not alter process environment variables.
    """
    token = _POLICY.set(resolve_policy(backend, allow_gee))
    try:
        yield
    finally:
        _POLICY.reset(token)


def require_gee_allowed():
    if not resolve_policy().allow_gee:
        raise ValueError(
            "GEE access is disabled by backend policy; select a supported direct source."
        )


def should_route_direct(source, backend=None):
    return source in DIRECT_SOURCES and resolve_policy(backend).backend != "gee"


def merge_provenance(*frames):
    result = []
    for frame in frames:
        for item in frame.attrs.get("data_provenance", []):
            if item not in result:
                result.append(item)
    return result


def save_frame_metadata(frame, output_path):
    """Keep provenance beside CSV/record JSON, which cannot carry frame attrs."""
    import json
    from pathlib import Path

    keys = ("data_provenance", "backend_attempts", "quality_control")
    metadata = {k: frame.attrs[k] for k in keys if k in frame.attrs}
    sidecar = Path(str(output_path) + ".metadata.json")
    if metadata:
        sidecar.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    else:
        # An overwritten CSV must not inherit the previous dataset's identity.
        sidecar.unlink(missing_ok=True)


def load_frame_metadata(frame, input_path):
    """Restore supported provenance fields when reopening a toolkit export."""
    import json
    from pathlib import Path

    sidecar = Path(str(input_path) + ".metadata.json")
    if sidecar.exists():
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError(f"Invalid metadata sidecar: {sidecar}")
        for key in ("data_provenance", "backend_attempts", "quality_control"):
            if key in metadata:
                frame.attrs[key] = metadata[key]
    return frame


def run_with_backend_policy(function, task, policy):
    """Picklable entry point preserving policy in spawned model workers."""
    with backend_policy(backend=policy.backend, allow_gee=policy.allow_gee):
        return function(task)
