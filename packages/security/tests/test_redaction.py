"""Field-name payload masking and credential-shaped text scrubbing."""

from security import MASKED, Redactor, redact_text

FIELDS = ("authorization", "api_key", "password")


def redactor(**kwargs) -> Redactor:
    return Redactor(FIELDS, **kwargs)


def test_masks_a_sensitive_field():
    assert redactor().payload({"api_key": "sk-live-123"}) == {"api_key": MASKED}


def test_field_matching_is_case_insensitive():
    assert redactor().payload({"Authorization": "Bearer x"}) == {"Authorization": MASKED}


def test_leaves_ordinary_fields_alone():
    assert redactor().payload({"name": "ada"}) == {"name": "ada"}


def test_masks_nested_mappings():
    payload = {"outer": {"password": "hunter2", "keep": 1}}
    assert redactor().payload(payload) == {"outer": {"password": MASKED, "keep": 1}}


def test_masks_inside_lists_and_preserves_the_type():
    payload = [{"api_key": "x"}, {"api_key": "y"}]
    assert redactor().payload(payload) == [{"api_key": MASKED}, {"api_key": MASKED}]


def test_masks_inside_tuples_and_preserves_the_type():
    result = redactor().payload(({"api_key": "x"},))
    assert isinstance(result, tuple)
    assert result == ({"api_key": MASKED},)


def test_prefix_matching_covers_per_instance_header_families():
    r = Redactor(FIELDS, prefixes=("x-binding-ref-",))
    payload = {"x-binding-ref-abc": "v", "x-binding-ref-def": "v"}
    assert r.payload(payload) == {"x-binding-ref-abc": MASKED, "x-binding-ref-def": MASKED}


def test_prefix_matching_does_not_match_a_bare_prefix():
    r = Redactor(FIELDS, prefixes=("x-binding-ref-",))
    assert r.payload({"x-binding-ref": "v"}) == {"x-binding-ref": "v"}


def test_placeholder_is_configurable():
    assert redactor(placeholder="***").payload({"password": "x"}) == {"password": "***"}


def test_non_string_keys_are_left_alone():
    assert redactor().payload({1: "v"}) == {1: "v"}


def test_scalars_pass_through_unchanged():
    assert redactor().payload("plain") == "plain"
    assert redactor().payload(None) is None
    assert redactor().payload(7) == 7


def test_is_sensitive_reports_the_decision():
    r = redactor()
    assert r.is_sensitive("API_KEY") is True
    assert r.is_sensitive("name") is False


def test_text_scrubs_url_credentials():
    assert redact_text("postgres://user:s3cret@db:5432/x") == "postgres://user:***@db:5432/x"


def test_text_scrubs_a_labelled_secret():
    assert MASKED in redact_text("password=hunter2")
    assert "hunter2" not in redact_text("password=hunter2")


def test_text_scrubs_a_bearer_token():
    scrubbed = redact_text("Authorization: Bearer abc.def.ghi")
    assert "abc.def.ghi" not in scrubbed
    assert MASKED in scrubbed


def test_text_scrubs_a_provider_shaped_key():
    assert "sk-live-abcdefghijklmnopqrst" not in redact_text("key sk-live-abcdefghijklmnopqrst")


def test_text_leaves_ordinary_prose_alone():
    assert redact_text("the token budget is 4096") == "the token budget is 4096"
