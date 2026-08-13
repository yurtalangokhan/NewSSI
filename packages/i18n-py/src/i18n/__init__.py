from .checker import check_missing_translations
from .core import LocaleManager, get_locale, init_service_i18n, normalize_locale, set_locale, t

try:
    from .middleware import I18nMiddleware
except ImportError:
    I18nMiddleware = None  # type: ignore[assignment, misc]

__all__ = [
    "LocaleManager",
    "get_locale",
    "set_locale",
    "normalize_locale",
    "t",
    "init_service_i18n",
    "I18nMiddleware",
    "check_missing_translations",
]
