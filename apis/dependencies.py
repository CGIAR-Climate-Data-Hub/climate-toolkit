from dotenv import load_dotenv

load_dotenv()


def get_settings():
    from climate_tookit.fetch_data.source_data.sources.utils.settings import Settings
    return Settings.load()
