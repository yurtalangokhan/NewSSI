import json
import logging
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Single source of truth for which locales this package ships translations
#: for. LocaleManager seeds its buckets from this, and normalize_locale
#: never returns anything outside it -- so the two cannot drift apart the
#: way two independently hardcoded ("en", "tr") literals could.
DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES: frozenset[str] = frozenset({"tr", "en"})

_current_locale: ContextVar[str] = ContextVar("current_locale", default=DEFAULT_LOCALE)


def get_locale() -> str:
    """Get the current request locale."""
    return _current_locale.get()


def set_locale(locale: str) -> Token[str]:
    """Set the current request locale."""
    return _current_locale.set(normalize_locale(locale))


def reset_locale(token: Token[str]) -> None:
    """Restore the locale that preceded a scoped request."""
    _current_locale.reset(token)


def _weighted_candidates(value: str) -> list[str]:
    """Parse an Accept-Language-style value into region-stripped locale
    codes, ordered by descending RFC 7231 SS5.3.5 quality (ties keep the
    header's original order). A bare single value (no q-value, no comma)
    is just one candidate at the implicit default quality of 1.0.
    """
    weighted: list[tuple[float, int, str]] = []
    for index, part in enumerate(value.split(",")):
        part = part.strip()
        if not part:
            continue
        tag, _, quality_str = part.partition(";q=")
        try:
            quality = float(quality_str) if quality_str else 1.0
        except ValueError:
            quality = 1.0
        tag = tag.strip().lower().replace("_", "-")
        code = tag.split("-")[0]
        if code:
            weighted.append((quality, index, code))

    # Stable-sort by quality descending; original order breaks ties, which
    # sorting by (-quality, index) achieves in one pass.
    weighted.sort(key=lambda item: (-item[0], item[1]))
    return [code for _quality, _index, code in weighted]


def normalize_locale(locale: str) -> str:
    """Resolve a locale/Accept-Language value to a supported locale code.

    Picks the highest-quality *supported* candidate rather than just the
    first entry: a client offering "fr-FR,tr;q=0.8" does not understand
    French but does accept Turkish, and must get "tr", not the "en"
    fallback that blindly taking the first entry would produce.
    """
    if not locale:
        return DEFAULT_LOCALE
    for code in _weighted_candidates(locale):
        if code in SUPPORTED_LOCALES:
            return code
    return DEFAULT_LOCALE


class LocaleManager:
    """Manages translation dictionaries and string lookups."""

    def __init__(self, default_locale: str = DEFAULT_LOCALE) -> None:
        self.default_locale = default_locale
        self.translations: Dict[str, Dict[str, str]] = {locale: {} for locale in SUPPORTED_LOCALES}

    def load_directory(self, directory_path: str | Path) -> None:
        """Load all JSON translation files from a directory."""
        path = Path(directory_path)
        if not path.exists() or not path.is_dir():
            return

        for file in path.glob("*.json"):
            locale = file.stem.lower()
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    flattened = self._flatten_dict(data)
                    if locale not in self.translations:
                        self.translations[locale] = {}
                    self.translations[locale].update(flattened)
            except (OSError, UnicodeError, ValueError):
                logger.exception("[i18n] Failed to load locale file %s", file)

    def _flatten_dict(
        self, d: Dict[str, Any], parent_key: str = "", sep: str = "."
    ) -> Dict[str, str]:
        """Flatten nested dictionary into dot-separated keys."""
        items: Dict[str, str] = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key, sep=sep))
            else:
                items[new_key] = str(v)
        return items

    def translate(
        self,
        key: str,
        default: Optional[str] = None,
        locale: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Translate a key into target locale with formatting support."""
        target_locale = normalize_locale(locale) if locale else get_locale()

        # 1. Look in target locale
        template = self.translations.get(target_locale, {}).get(key)

        # 2. Fallback to default locale ('en') if missing
        if template is None and target_locale != self.default_locale:
            template = self.translations.get(self.default_locale, {}).get(key)

        # 3. Fallback to default arg or key itself
        if template is None:
            template = default if default is not None else key

        # Interpolate variables safely
        if kwargs:
            try:
                return template.format(**kwargs)
            except (KeyError, ValueError, IndexError):
                # Safe fallback if formatting fails
                res = template
                for k, v in kwargs.items():
                    res = res.replace("{" + k + "}", str(v))
                return res
        return template


# Global instance
_manager = LocaleManager()


def init_localization(locales_dir: str | Path) -> LocaleManager:
    """Initialize i18n for a service by loading its locales directory."""
    _manager.load_directory(locales_dir)
    return _manager


def t(key: str, default: Optional[str] = None, locale: Optional[str] = None, **kwargs: Any) -> str:
    """Translate function shortcut."""
    return _manager.translate(key, default=default, locale=locale, **kwargs)
