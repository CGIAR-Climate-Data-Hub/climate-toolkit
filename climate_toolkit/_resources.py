"""Helpers for loading packaged toolkit resources."""

from __future__ import annotations

from contextlib import contextmanager
from importlib.resources import as_file, files
import json
from pathlib import Path
from typing import Any, Iterator

import yaml


def package_resource_exists(package: str, resource_name: str) -> bool:
    """Return True when a packaged resource is available."""
    return files(package).joinpath(resource_name).is_file()


def _require_package_resource(package: str, resource_name: str) -> Any:
    resource = files(package).joinpath(resource_name)
    if not resource.is_file():
        raise FileNotFoundError(f"Missing packaged resource {package}:{resource_name}")
    return resource


@contextmanager
def packaged_resource_path(package: str, resource_name: str) -> Iterator[Path]:
    """Yield a real filesystem path for a packaged resource."""
    resource = _require_package_resource(package, resource_name)
    with as_file(resource) as path:
        yield path


def load_json_resource(package: str, resource_name: str) -> Any:
    """Load a packaged JSON resource."""
    resource = _require_package_resource(package, resource_name)
    with resource.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_yaml_resource(package: str, resource_name: str) -> Any:
    """Load a packaged YAML resource."""
    resource = _require_package_resource(package, resource_name)
    with resource.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)
