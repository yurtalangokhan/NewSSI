from .checker import check_missing_translations
from .core import LocaleManager, get_locale, init_localization, normalize_locale, set_locale, t

# starlette is a required dependency (see pyproject.toml), not an optional
# extra, so this import is never expected to fail. Importing it directly
# rather than behind a try/except keeps a real bug in middleware.py a loud
# ImportError at startup instead of a silent LocalizationMiddleware = None that
# fails much later with an unrelated "NoneType is not callable".
from .middleware import LocalizationMiddleware

__all__ = [
    "LocaleManager",
    "get_locale",
    "set_locale",
    "normalize_locale",
    "t",
    "init_localization",
    "LocalizationMiddleware",
    "check_missing_translations",
]
