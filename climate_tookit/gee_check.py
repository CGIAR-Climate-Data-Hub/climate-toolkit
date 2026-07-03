"""Earth Engine preflight check — ``climate-toolkit-gee-check``.

A fast, standalone diagnostic that verifies Earth Engine is ready *before*
long downloads start, and turns the usual deep-in-a-workflow stack traces into
one clear, actionable message. It distinguishes:

- missing / placeholder project ID
- missing authentication
- invalid / deleted project (or wrong Google account)
- network / DNS / auth-refresh failure

and runs a tiny ``ee.Number(1).getInfo()`` round-trip as the final success
check. All remediation hints include both bash and Windows PowerShell commands
and a link to the README setup section.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Tuple

from .fetch_data.source_data.sources.xee_common import (
    EARTH_ENGINE_SETUP_URL,
    import_xee_stack,
    initialize_earth_engine,
)

PROJECT_ENV_VARS = ("GCP_PROJECT_ID", "GOOGLE_CLOUD_PROJECT", "EE_PROJECT_ID")

# Common literal placeholders users paste without editing.
PLACEHOLDER_PROJECT_IDS = frozenset(
    {
        "your-ee-project-id",
        "your-project-id",
        "your_project_id",
        "your-gcp-project-id",
        "yourprojectid",
        "project-id",
        "changeme",
        "ee-project-id",
    }
)


def resolve_project_id(explicit: Optional[str] = None) -> Optional[str]:
    """Return the first non-empty project ID from the argument or env vars."""
    for value in (explicit, *(os.getenv(name) for name in PROJECT_ENV_VARS)):
        if value and value.strip():
            return value.strip()
    return None


def is_placeholder_project_id(project_id: Optional[str]) -> bool:
    """True if the value looks like unedited placeholder text (e.g. YOUR_PROJECT_ID)."""
    if not project_id:
        return False
    normalized = project_id.strip().lower()
    if normalized in PLACEHOLDER_PROJECT_IDS:
        return True
    if normalized.startswith("<") or normalized.endswith(">"):
        return True
    return "your" in normalized and "project" in normalized


def classify_ee_error(exc: Exception) -> str:
    """Bucket an Earth Engine failure into a diagnostic category.

    Returns one of: ``"auth"``, ``"project"``, ``"network"``, ``"unknown"``.
    """
    message = str(exc).lower()
    auth_markers = (
        "please authorize",
        "earthengine authenticate",
        "not signed in",
        "no credentials",
        "credentials",
        "invalid_grant",
        "reauth",
        "please run",
    )
    project_markers = (
        "not found or deleted",
        "not found",
        "does not exist",
        "not registered to use earth engine",
        "permission denied",
        "permission_denied",
        "caller does not have permission",
        "403",
        "is not registered",
    )
    network_markers = (
        "failed to resolve",
        "max retries exceeded",
        "transporterror",
        "oauth2.googleapis.com",
        "connection reset",
        "connection aborted",
        "temporarily unavailable",
        "timed out",
        "timeout",
        "getaddrinfo",
    )
    # Network first: a DNS failure can otherwise read as an auth/credential error.
    if any(marker in message for marker in network_markers):
        return "network"
    if any(marker in message for marker in auth_markers):
        return "auth"
    if any(marker in message for marker in project_markers):
        return "project"
    return "unknown"


def _setup_link() -> str:
    return f"See the setup guide: {EARTH_ENGINE_SETUP_URL}"


def _auth_hint() -> str:
    return (
        "Authenticate with your Google Earth Engine account:\n"
        "  bash:        python -c \"import ee; ee.Authenticate()\"\n"
        "  PowerShell:  python -c \"import ee; ee.Authenticate()\"\n"
        "Make sure you sign in with the Google account registered for Earth Engine.\n"
        f"{_setup_link()}"
    )


def _missing_project_hint() -> str:
    return (
        "No Earth Engine project ID found. Set one of "
        f"{', '.join(PROJECT_ENV_VARS)} to your real Google Cloud Project ID:\n"
        "  bash:        export GCP_PROJECT_ID=my-ee-project\n"
        "  PowerShell:  $env:GCP_PROJECT_ID = \"my-ee-project\"\n"
        f"{_setup_link()}"
    )


def _placeholder_project_hint(project_id: str) -> str:
    return (
        f"The project ID '{project_id}' looks like unedited placeholder text. "
        "Replace it with your real Google Cloud Project ID:\n"
        "  bash:        export GCP_PROJECT_ID=my-ee-project\n"
        "  PowerShell:  $env:GCP_PROJECT_ID = \"my-ee-project\"\n"
        f"{_setup_link()}"
    )


def _project_error_hint(project_id: str, detail: str) -> str:
    return (
        f"Earth Engine rejected project '{project_id}'. This usually means the "
        "project does not exist / was deleted, is not registered for Earth "
        "Engine, or you authenticated with a Google account that lacks access "
        "to it.\n"
        "  - Confirm the Project ID (not the project *name* or *number*).\n"
        "  - Register it for Earth Engine and confirm your account has access.\n"
        "  - If you use several Google accounts, re-run "
        "`python -c \"import ee; ee.Authenticate()\"` and pick the right one.\n"
        f"Underlying error: {detail}\n"
        f"{_setup_link()}"
    )


def _network_error_hint(detail: str) -> str:
    return (
        "Could not reach Earth Engine / Google auth servers. Check your "
        "internet and DNS, then retry. If you are behind a proxy or VPN, make "
        "sure it allows googleapis.com.\n"
        f"Underlying error: {detail}\n"
        f"{_setup_link()}"
    )


def _credentials_present(ee_module) -> Optional[bool]:
    """Best-effort local check for stored EE credentials.

    Returns True/False when it can tell, or None when it cannot (in which case
    the caller should let ``Initialize`` make the determination).
    """
    if os.getenv("EARTHENGINE_TOKEN"):
        return True
    try:
        path = ee_module.oauth.get_credentials_path()
    except Exception:
        return None
    try:
        return os.path.exists(path)
    except Exception:
        return None


def run_preflight(project_id: Optional[str], writer=print) -> Tuple[int, str]:
    """Run the staged Earth Engine checks.

    Returns ``(exit_code, category)`` where category is ``"ok"`` on success or
    one of the ``classify_ee_error`` buckets / ``"project-missing"`` /
    ``"project-placeholder"`` / ``"import"`` on failure.
    """
    resolved = resolve_project_id(project_id)

    if not resolved:
        writer(_missing_project_hint())
        return 1, "project-missing"
    if is_placeholder_project_id(resolved):
        writer(_placeholder_project_hint(resolved))
        return 1, "project-placeholder"

    writer(f"Project ID: {resolved}")

    try:
        ee_module, _ = import_xee_stack("climate-toolkit-gee-check")
    except ImportError as exc:
        writer(str(exc))
        return 1, "import"

    if _credentials_present(ee_module) is False:
        writer("Earth Engine authentication not found.")
        writer(_auth_hint())
        return 1, "auth"

    try:
        initialize_earth_engine(ee_module, project_id=resolved)
    except Exception as exc:  # noqa: BLE001 - classify and explain, don't leak trace
        category = classify_ee_error(exc)
        if category == "auth":
            writer(_auth_hint())
        elif category == "project":
            writer(_project_error_hint(resolved, str(exc)))
        elif category == "network":
            writer(_network_error_hint(str(exc)))
        else:
            writer(f"Earth Engine initialization failed: {exc}\n{_setup_link()}")
        return 1, category

    try:
        value = ee_module.Number(1).getInfo()
    except Exception as exc:  # noqa: BLE001
        category = classify_ee_error(exc)
        if category == "network":
            writer(_network_error_hint(str(exc)))
        elif category == "project":
            writer(_project_error_hint(resolved, str(exc)))
        else:
            writer(f"Earth Engine round-trip failed: {exc}\n{_setup_link()}")
        return 1, category if category != "unknown" else "roundtrip"

    if value != 1:
        writer(f"Unexpected Earth Engine response ({value!r}); expected 1.")
        return 1, "roundtrip"

    writer("Earth Engine is ready. Authentication, project, and a live "
           "round-trip (ee.Number(1).getInfo()) all succeeded.")
    return 0, "ok"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="climate-toolkit-gee-check",
        description=(
            "Preflight check for Earth Engine setup. Verifies project ID, "
            "authentication, and a live round-trip before running workflows."
        ),
    )
    parser.add_argument(
        "--project",
        default=None,
        help=(
            "Earth Engine project ID to test. Defaults to "
            f"{', '.join(PROJECT_ENV_VARS)} from the environment."
        ),
    )
    args = parser.parse_args(argv)

    exit_code, _ = run_preflight(args.project)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
