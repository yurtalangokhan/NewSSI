import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Optional

_current_locale: ContextVar[str] = ContextVar("current_locale", default="en")


def get_locale() -> str:
    """Get the current request locale."""
    return _current_locale.get()


def set_locale(locale: str) -> None:
    """Set the current request locale."""
    _current_locale.set(normalize_locale(locale))


def normalize_locale(locale: str) -> str:
    """Normalize locale string (e.g. 'tr-TR' -> 'tr', 'en-US' -> 'en')."""
    if not locale:
        return "en"
    clean = locale.split(",")[0].split(";")[0].strip().lower()
    if "-" in clean:
        clean = clean.split("-")[0]
    if "_" in clean:
        clean = clean.split("_")[0]
    return clean if clean in ("tr", "en") else "en"


class LocaleManager:
    """Manages translation dictionaries and string lookups."""

    def __init__(self, default_locale: str = "en") -> None:
        self.default_locale = default_locale
        self.translations: Dict[str, Dict[str, str]] = {"en": {}, "tr": {}}

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
            except Exception as e:
                print(f"[i18n] Failed to load {file}: {e}")

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


def init_service_i18n(locales_dir: str | Path) -> LocaleManager:
    """Initialize i18n for a service by loading its locales directory."""
    _manager.load_directory(locales_dir)
    return _manager


def t(key: str, default: Optional[str] = None, locale: Optional[str] = None, **kwargs: Any) -> str:
    """Translate function shortcut."""
    return _manager.translate(key, default=default, locale=locale, **kwargs)
