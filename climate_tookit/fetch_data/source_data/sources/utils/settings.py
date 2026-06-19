"""This module contains settings and paths for the `source_data` module"""

import logging
from pathlib import Path

from climate_tookit._resources import load_yaml_resource
import yaml
from pydantic import BaseModel, field_validator

CONFIG_PACKAGE = "climate_tookit.fetch_data.source_data.sources.utils"
CONFIG_RESOURCE = "config.yaml"
TOOLKIT_LOGGER_NAME = "climate_tookit"

def set_logging():
    """Configure toolkit logger without mutating root logging state."""
    logger = logging.getLogger(TOOLKIT_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(filename)s:%(lineno)d --- %(message)s"
            )
        )
        logger.addHandler(handler)
    return logger


class Cadence(BaseModel):
    monthly: str
    daily: str
    half_hourly: str

class VariableMeta(BaseModel):
    band: str
    units: str | None = None
    scale: float = 1.0


class ClimateVariable(BaseModel):
    precipitation: VariableMeta | None = None
    max_temperature: VariableMeta | None = None
    min_temperature: VariableMeta | None = None
    mean_temperature: VariableMeta | None = None
    humidity: VariableMeta | None = None
    wind_speed: VariableMeta | None = None
    solar_radiation: VariableMeta | None = None
    soil_moisture: VariableMeta | None = None
    
    def get_band(self, var_name: str) -> str | None:
        meta = getattr(self, var_name, None)
        return meta.band if meta else None

    @field_validator("*", mode="before")
    @classmethod
    def allow_string(cls, v):
        if isinstance(v, str):
            return {"band": v}
        return v

class SoilVariable(BaseModel):
    root_depth: str | None = None
    available_water_capacity: str | None = None
    drainage: str | None = None
    bulk_density: str | None = None
    field_capacity: str | None = None
    coarse_fragments: str | None = None
    wilting_point: str | None = None
    clay_content: str | None = None
    ph: str | None = None
    sand_content: str | None = None
    silt_content: str | None = None
    organic_carbon: str | None = None
    organic_carbon_stock: str | None = None
    soil_moisture: str | None = None
    cation_exchange_capacity: str | None = None

    def get_band(self, var_name: str) -> str | None:
        """Return the band name for a given soil variable."""
        return getattr(self, var_name, None)

class Agera5Settings(BaseModel):
    gee_image: str
    cadence: str
    variable: ClimateVariable
    resolution: float = 0.25


class Era5Settings(BaseModel):
    request: dict
    gee_image: str
    resolution: float
    variable: ClimateVariable
    cadence: str


class ImergSettings(BaseModel):
    version: str
    short_name: Cadence
    gee_image: str
    resolution: float
    variable: ClimateVariable
    cadence: str


class TerraSettings(BaseModel):
    url: str
    variable: ClimateVariable
    gee_image: str
    resolution: float
    cadence: str


class ChirtsSettings(BaseModel):
    gee_image: str
    resolution: float
    cadence: str
    variable: ClimateVariable
    
class ChirpsSettings(BaseModel):
    gee_image: str
    resolution: float
    variable: ClimateVariable
    cadence: str


class ChirpsV3DailyRnlSettings(BaseModel):
    gee_image: str
    resolution: float
    variable: ClimateVariable
    cadence: str

class Cmip6Settings(BaseModel):
    gee_image: str
    resolution: float
    cadence: str
    variable: ClimateVariable
    
class NexGddpSettings(BaseModel):
    gee_image: str
    resolution: float
    cadence: str
    variable: ClimateVariable
    
class NasaPowerSettings(BaseModel):
    endpoint: str
    parameters: list[str]
    temporal_api: str
    resolution: float
    variable: ClimateVariable
    cadence: str

class TamsatSettings(BaseModel):
    rainfall_url: str
    rainfall_zip_url: str | None = None
    soil_moisture_url: str
    data_format: str
    download_format: str
    cadence: str
    resolution: float
    variable: ClimateVariable

class SoilGridSettings(BaseModel):
    # Support both single image (backward compatibility) and multiple images
    gee_image: str | None = None
    gee_images: dict[str, str | None] | None = None
    cadence: str
    resolution: float
    variable: SoilVariable
 
    @property
    def has_multiple_images(self) -> bool:
        """Check if this configuration uses multiple GEE images."""
        return self.gee_images is not None and len(self.gee_images) > 0
 
    def get_image_for_variable(self, variable_name: str) -> str | None:
        """Get the appropriate GEE image for a given variable."""
        if self.has_multiple_images:
            return self.gee_images.get(variable_name)
        return self.gee_image

class Settings(BaseModel):
    """Loads the application's settings."""

    agera_5: Agera5Settings
    era_5: Era5Settings
    imerg: ImergSettings
    terraclimate: TerraSettings
    chirts: ChirtsSettings
    chirps_v2: ChirpsSettings
    chirps_v3_daily_rnl: ChirpsV3DailyRnlSettings
    cmip_6: Cmip6Settings
    nex_gddp: NexGddpSettings
    nasa_power: NasaPowerSettings
    tamsat: TamsatSettings
    soil_grid: SoilGridSettings
    hwsd: SoilGridSettings

    @classmethod
    def load(cls, settings_path: str | Path | None = None):
        if settings_path is None:
            settings = load_yaml_resource(CONFIG_PACKAGE, CONFIG_RESOURCE)
        else:
            with Path(settings_path).open(mode="r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)
        return cls(**settings)
