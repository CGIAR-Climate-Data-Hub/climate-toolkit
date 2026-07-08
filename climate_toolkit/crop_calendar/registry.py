"""Shared crop support registry.

Calendar support can be broader than hazard-threshold or water-balance support.
Keep those distinctions explicit so callers do not over-promise functionality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def _slug(value: str) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


@dataclass(frozen=True)
class CropSupport:
    canonical_name: str
    ggcmi_codes: tuple[str, ...]
    aliases: tuple[str, ...]
    calendar_supported: bool
    hazard_thresholds_supported: bool
    water_balance_params_supported: bool


_CROPS: tuple[CropSupport, ...] = (
    CropSupport("Barley", ("bar",), ("barley",), True, False, False),
    CropSupport("Beans", ("bea",), ("bean", "beans", "commonbean", "commonbeans"), True, True, True),
    CropSupport("Cassava", ("cas",), ("cassava", "manioc"), True, True, True),
    CropSupport("Cotton", ("cot",), ("cotton",), True, False, False),
    CropSupport("Groundnuts", ("nut",), ("groundnut", "groundnuts", "peanut", "peanuts"), True, True, True),
    CropSupport("Maize", ("mai",), ("maize", "corn"), True, True, True),
    CropSupport("Millet", ("mil",), ("millet", "millets"), True, True, True),
    CropSupport("Peas", ("pea",), ("pea", "peas"), True, False, False),
    CropSupport("Potato", ("pot",), ("potato", "potatoes"), True, False, False),
    CropSupport("Rapeseed", ("rap",), ("rapeseed", "canola", "oilseedrape"), True, False, False),
    CropSupport("Rice", ("ri1", "ri2"), ("rice", "paddy"), True, True, True),
    CropSupport("Rye", ("rye",), ("rye",), True, False, False),
    CropSupport("Sorghum", ("sor",), ("sorghum",), True, True, True),
    CropSupport("Soybean", ("soy",), ("soybean", "soybeans", "soy"), True, False, False),
    CropSupport("Spring Wheat", ("swh",), ("springwheat", "spring_wheat"), True, False, False),
    CropSupport("Sugar Beet", ("sgb",), ("sugarbeet", "sugar_beet"), True, False, False),
    CropSupport("Sugarcane", ("sgc",), ("sugarcane", "sugar_cane"), True, False, False),
    CropSupport("Sunflower", ("sun",), ("sunflower",), True, False, False),
    CropSupport("Winter Wheat", ("wwh",), ("winterwheat", "winter_wheat"), True, False, False),
)

_BY_SLUG = {}
for crop in _CROPS:
    _BY_SLUG[_slug(crop.canonical_name)] = crop
    for alias in crop.aliases:
        _BY_SLUG[_slug(alias)] = crop


def get_crop_support(crop_name: str) -> CropSupport | None:
    return _BY_SLUG.get(_slug(crop_name))


def normalize_crop_name(
    crop_name: str,
    *,
    require_calendar: bool = False,
    require_hazard_thresholds: bool = False,
    require_water_balance_params: bool = False,
) -> str:
    crop = get_crop_support(crop_name)
    if crop is None:
        raise ValueError(
            f"Unknown crop: {crop_name}. Available: {', '.join(supported_crop_names())}"
        )
    if require_calendar and not crop.calendar_supported:
        raise ValueError(f"Crop '{crop.canonical_name}' does not have calendar support.")
    if require_hazard_thresholds and not crop.hazard_thresholds_supported:
        raise ValueError(
            f"Crop '{crop.canonical_name}' has calendar support but no hazard thresholds yet."
        )
    if require_water_balance_params and not crop.water_balance_params_supported:
        raise ValueError(
            f"Crop '{crop.canonical_name}' has calendar support but no crop water-balance parameters yet."
        )
    return crop.canonical_name


def supported_crop_names() -> list[str]:
    return sorted(crop.canonical_name for crop in _CROPS)


def calendar_supported_crop_names() -> list[str]:
    return sorted(crop.canonical_name for crop in _CROPS if crop.calendar_supported)


def threshold_supported_crop_names() -> list[str]:
    return sorted(crop.canonical_name for crop in _CROPS if crop.hazard_thresholds_supported)


def water_balance_supported_crop_names() -> list[str]:
    return sorted(crop.canonical_name for crop in _CROPS if crop.water_balance_params_supported)


def iter_crops() -> Iterable[CropSupport]:
    return tuple(_CROPS)
