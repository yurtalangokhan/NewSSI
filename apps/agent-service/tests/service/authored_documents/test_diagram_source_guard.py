import pytest

from service.authored_documents.diagram_source_guard import unsafe_image_reference


@pytest.mark.parametrize(
    "source, reference",
    [
        ("<img src=/etc/passwd>", "/etc/passwd"),
        ("<img alt=x src=/etc/passwd width=3>", "/etc/passwd"),
        ("<img src='/etc/passwd'>", "/etc/passwd"),
        ('<img src=\\"/etc/passwd\\">', "/etc/passwd"),
        ('<image xlink:href="file:///etc/passwd"/>', "file:///etc/passwd"),
        ("<image href=/etc/passwd/>", "/etc/passwd/"),
        ("A@{ img: /etc/passwd, label: x }", "/etc/passwd"),
        ("A@{ img: '/etc/passwd', label: x }", "/etc/passwd"),
        ('<img src="&#47;etc/passwd">', "&#47;etc/passwd"),
        ('<img src="  file:///etc/passwd">', "file:///etc/passwd"),
    ],
)
def test_local_references_are_detected_in_every_attribute_form(source: str, reference: str) -> None:
    found = unsafe_image_reference(source)
    assert found is not None and found == (1, reference)


@pytest.mark.parametrize(
    "source",
    [
        "<img src=data:image/png;base64,AAAA>",
        "<img src='https://example.com/a.png'>",
        '<img src="HTTP://example.com/a.png">',
        "A@{ img: https://example.com/a.png, label: x }",
        "flowchart LR\n  A --> B",
    ],
)
def test_inline_and_remote_references_are_allowed(source: str) -> None:
    assert unsafe_image_reference(source) is None
