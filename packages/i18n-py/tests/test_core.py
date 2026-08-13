import json
from pathlib import Path

import pytest

from i18n.core import LocaleManager, get_locale, normalize_locale, set_locale


class TestNormalizeLocale:
    def test_passthrough_supported_locale(self):
        assert normalize_locale("tr") == "tr"
        assert normalize_locale("en") == "en"

    def test_strips_region_subtag(self):
        assert normalize_locale("tr-TR") == "tr"
        assert normalize_locale("en-US") == "en"

    def test_strips_underscore_region_subtag(self):
        assert normalize_locale("tr_TR") == "tr"

    def test_takes_first_entry_of_accept_language_list(self):
        assert normalize_locale("tr-TR,tr;q=0.9,en;q=0.8") == "tr"

    def test_unsupported_locale_falls_back_to_en(self):
        assert normalize_locale("fr") == "en"
        assert normalize_locale("de-DE") == "en"

    def test_empty_or_none_falls_back_to_en(self):
        assert normalize_locale("") == "en"
        assert normalize_locale(None) == "en"  # type: ignore[arg-type]

    def test_is_case_insensitive(self):
        assert normalize_locale("TR") == "tr"
        assert normalize_locale("EN-us") == "en"


class TestLocaleContext:
    def test_default_locale_is_en(self):
        assert get_locale() == "en"

    def test_set_locale_updates_current_context(self):
        set_locale("tr")
        try:
            assert get_locale() == "tr"
        finally:
            set_locale("en")

    def test_set_locale_normalizes_input(self):
        set_locale("tr-TR")
        try:
            assert get_locale() == "tr"
        finally:
            set_locale("en")

    @pytest.mark.asyncio
    async def test_locale_is_isolated_per_async_task(self):
        import asyncio

        results = {}

        async def worker(name: str, locale: str, delay: float):
            set_locale(locale)
            await asyncio.sleep(delay)
            results[name] = get_locale()

        await asyncio.gather(
            worker("a", "tr", 0.02),
            worker("b", "en", 0.01),
        )

        assert results == {"a": "tr", "b": "en"}


class TestLocaleManagerLoadDirectory:
    def test_loads_json_files_by_stem_as_locale(self, tmp_path: Path):
        (tmp_path / "en.json").write_text(json.dumps({"greeting": "Hello"}), encoding="utf-8")
        (tmp_path / "tr.json").write_text(json.dumps({"greeting": "Merhaba"}), encoding="utf-8")

        manager = LocaleManager()
        manager.load_directory(tmp_path)

        assert manager.translations["en"]["greeting"] == "Hello"
        assert manager.translations["tr"]["greeting"] == "Merhaba"

    def test_flattens_nested_keys_with_dot_separator(self, tmp_path: Path):
        (tmp_path / "en.json").write_text(
            json.dumps({"agent": {"not_found": "Agent not found"}}), encoding="utf-8"
        )

        manager = LocaleManager()
        manager.load_directory(tmp_path)

        assert manager.translations["en"]["agent.not_found"] == "Agent not found"

    def test_missing_directory_is_a_silent_noop(self, tmp_path: Path):
        manager = LocaleManager()
        manager.load_directory(tmp_path / "does-not-exist")
        assert manager.translations == {"en": {}, "tr": {}}

    def test_invalid_json_is_skipped_without_raising(self, tmp_path: Path):
        (tmp_path / "en.json").write_text("{not valid json", encoding="utf-8")

        manager = LocaleManager()
        manager.load_directory(tmp_path)  # must not raise

        assert manager.translations["en"] == {}

    def test_loading_twice_merges_rather_than_overwrites_other_keys(self, tmp_path: Path):
        (tmp_path / "en.json").write_text(json.dumps({"a": "A"}), encoding="utf-8")
        manager = LocaleManager()
        manager.load_directory(tmp_path)

        (tmp_path / "en.json").write_text(json.dumps({"b": "B"}), encoding="utf-8")
        manager.load_directory(tmp_path)

        assert manager.translations["en"] == {"a": "A", "b": "B"}


class TestLocaleManagerTranslate:
    @pytest.fixture
    def manager(self) -> LocaleManager:
        m = LocaleManager()
        m.translations = {
            "en": {"greeting": "Hello {name}", "farewell": "Bye"},
            "tr": {"greeting": "Merhaba {name}"},
        }
        return m

    def test_translates_in_requested_locale(self, manager: LocaleManager):
        assert manager.translate("greeting", locale="tr", name="Ali") == "Merhaba Ali"

    def test_falls_back_to_default_locale_when_key_missing_in_target(self, manager: LocaleManager):
        # "farewell" only exists in en; requesting tr should fall back to en.
        assert manager.translate("farewell", locale="tr") == "Bye"

    def test_falls_back_to_key_itself_when_missing_everywhere(self, manager: LocaleManager):
        assert manager.translate("does.not.exist", locale="tr") == "does.not.exist"

    def test_falls_back_to_explicit_default_when_missing_everywhere(self, manager: LocaleManager):
        result = manager.translate("does.not.exist", default="Fallback text", locale="tr")
        assert result == "Fallback text"

    def test_uses_context_locale_when_locale_arg_omitted(self, manager: LocaleManager):
        set_locale("tr")
        try:
            assert manager.translate("greeting", name="Ali") == "Merhaba Ali"
        finally:
            set_locale("en")

    def test_missing_format_kwarg_does_not_raise(self, manager: LocaleManager):
        # Template needs {name} but none is supplied — must not throw KeyError.
        result = manager.translate("greeting", locale="en")
        assert result == "Hello {name}"

    def test_extra_format_kwargs_do_not_raise(self, manager: LocaleManager):
        result = manager.translate("farewell", locale="en", unused="x")
        assert result == "Bye"

    def test_no_kwargs_returns_template_unformatted(self, manager: LocaleManager):
        assert manager.translate("greeting", locale="en") == "Hello {name}"


class TestLocaleManagerDefaultLocaleConfigurable:
    def test_custom_default_locale_used_for_fallback(self):
        manager = LocaleManager(default_locale="tr")
        manager.translations = {"en": {}, "tr": {"only_tr": "Sadece Turkce"}}
        assert manager.translate("only_tr", locale="en") == "Sadece Turkce"
