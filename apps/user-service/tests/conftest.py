from pathlib import Path

from i18n import init_service_i18n

init_service_i18n(Path(__file__).resolve().parents[1] / "locales")
