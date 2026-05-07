import re
from copy import copy
from dataclasses import dataclass
from io import BytesIO
from typing import IO

import logging
from enum import Enum

import bs4

logger = logging.getLogger(__name__)


class HtmlBasedConnectorTransformLinksStrategy(Enum):
    STRIP = "strip"
    MARKDOWN = "markdown"


HTML_BASED_CONNECTOR_TRANSFORM_LINKS_STRATEGY = HtmlBasedConnectorTransformLinksStrategy.STRIP
PARSE_WITH_TRAFILATURA = True
WEB_CONNECTOR_IGNORED_CLASSES: list[str] = []
WEB_CONNECTOR_IGNORED_ELEMENTS: list[str] = []

MINTLIFY_UNWANTED = ["sticky", "hidden"]
NON_CONTENT_TAGS = ["script", "style", "noscript", "template"]

# Semantic HTML5 tags that are structurally noise (navigation, chrome, sidebars)
NOISE_SEMANTIC_TAGS = ["nav", "header", "footer", "aside"]

# Tags that define the content root — never removed by noise filters
_STRUCTURAL_TAGS = frozenset(["html", "head", "body", "main", "article", "section"])

# ARIA landmark roles that indicate non-content regions
NOISE_ARIA_ROLES = ["navigation", "banner", "complementary", "contentinfo"]

# CSS class / id substrings that reliably indicate noise.
# Matched as substrings (case-insensitive) against both class and id attributes.
NOISE_CLASS_PATTERNS = [
    "nav",
    "navbar",
    "menu",
    "sidebar",
    "widget",
    "breadcrumb",
    "cookie",
    "consent",
    "gdpr",
    "advertisement",
    "sponsor",
    "social-share",
    "share-bar",
    "related-posts",
    "recommended",
    "popup",
    "modal",
    "overlay",
    "banner",
]


@dataclass
class ParsedHTML:
    title: str | None
    cleaned_text: str


def _select_content_root(soup: bs4.BeautifulSoup) -> bs4.BeautifulSoup | bs4.element.Tag:
    """Prefer content-bearing regions over full-document parsing.

    Priority:
    1) <article> when present (news/blog pages)
    2) <main> / role=main
    3) <body>
    4) full soup as a last resort
    """
    body = soup.body
    if body is None:
        return soup

    article = body.find("article")
    if isinstance(article, bs4.element.Tag):
        return article

    main = body.find("main")
    if isinstance(main, bs4.element.Tag):
        return main

    role_main = body.find(attrs={"role": "main"})
    if isinstance(role_main, bs4.element.Tag):
        return role_main

    return body


def strip_excessive_newlines_and_spaces(document: str) -> str:
    # collapse repeated spaces into one
    document = re.sub(r" +", " ", document)
    # remove trailing spaces
    document = re.sub(r" +[\n\r]", "\n", document)
    # remove repeated newlines
    document = re.sub(r"[\n\r]+", "\n", document)
    return document.strip()


def strip_newlines(document: str) -> str:
    # HTML might contain newlines which are just whitespaces to a browser
    return re.sub(r"[\n\r]+", " ", document)


def format_element_text(element_text: str, link_href: str | None) -> str:
    element_text_no_newlines = strip_newlines(element_text)

    if (
        not link_href
        or HTML_BASED_CONNECTOR_TRANSFORM_LINKS_STRATEGY
        == HtmlBasedConnectorTransformLinksStrategy.STRIP
    ):
        return element_text_no_newlines

    return f"[{element_text_no_newlines}]({link_href})"


def parse_html_with_trafilatura(html_content: str) -> str:
    """Parse HTML content using trafilatura."""
    import trafilatura
    from trafilatura.settings import use_config

    config = use_config()
    config.set("DEFAULT", "include_links", "True")
    config.set("DEFAULT", "include_tables", "True")
    config.set("DEFAULT", "include_images", "True")
    config.set("DEFAULT", "include_formatting", "True")

    extracted_text = trafilatura.extract(html_content, config=config)
    return strip_excessive_newlines_and_spaces(extracted_text) if extracted_text else ""


def format_document_soup(
    document: bs4.BeautifulSoup, table_cell_separator: str = "\t"
) -> str:
    """Format html to a flat text document.

    The following goals:
    - Newlines from within the HTML are removed (as browser would ignore them as well).
    - Repeated newlines/spaces are removed (as browsers would ignore them).
    - Newlines only before and after headlines and paragraphs or when explicit (br or pre tag)
    - Table columns/rows are separated by newline
    - List elements are separated by newline and start with a hyphen
    """
    text = ""
    list_element_start = False
    verbatim_output = 0
    in_table = False
    last_added_newline = False
    link_href: str | None = None

    for e in document.descendants:
        verbatim_output -= 1
        if isinstance(e, bs4.element.NavigableString):
            if isinstance(e, (bs4.element.Comment, bs4.element.Doctype)):
                continue
            element_text = e.text
            if in_table:
                # Tables are represented in natural language with rows separated by newlines
                # Can't have newlines then in the table elements
                element_text = element_text.replace("\n", " ").strip()

            # Some tags are translated to spaces but in the logic underneath this section, we
            # translate them to newlines as a browser should render them such as with br
            # This logic here avoids a space after newline when it shouldn't be there.
            if last_added_newline and element_text.startswith(" "):
                element_text = element_text[1:]
                last_added_newline = False

            if element_text:
                content_to_add = (
                    element_text
                    if verbatim_output > 0
                    else format_element_text(element_text, link_href)
                )

                # Don't join separate elements without any spacing
                if (text and not text[-1].isspace()) and (
                    content_to_add and not content_to_add[0].isspace()
                ):
                    text += " "

                text += content_to_add

                list_element_start = False
        elif isinstance(e, bs4.element.Tag):
            # table is standard HTML element
            if e.name == "table":
                in_table = True
            # tr is for rows
            elif e.name == "tr" and in_table:
                text += "\n"
            # td for data cell, th for header
            elif e.name in ["td", "th"] and in_table:
                text += table_cell_separator
            elif e.name == "/table":
                in_table = False
            elif in_table:
                # don't handle other cases while in table
                pass
            elif e.name == "a":
                href_value = e.get("href", None)
                # mostly for typing, having multiple hrefs is not valid HTML
                link_href = (
                    href_value[0] if isinstance(href_value, list) else href_value
                )
            elif e.name == "/a":
                link_href = None
            elif e.name in ["p", "div"]:
                if not list_element_start:
                    text += "\n"
            elif e.name in ["h1", "h2", "h3", "h4"]:
                text += "\n"
                list_element_start = False
                last_added_newline = True
            elif e.name == "br":
                text += "\n"
                list_element_start = False
                last_added_newline = True
            elif e.name == "li":
                text += "\n- "
                list_element_start = True
            elif e.name == "pre":
                if verbatim_output <= 0:
                    verbatim_output = len(list(e.childGenerator()))
    return strip_excessive_newlines_and_spaces(text)


def parse_html_page_basic(text: str | BytesIO | IO[bytes]) -> str:
    soup = bs4.BeautifulSoup(text, "lxml")
    return format_document_soup(soup)


def _remove_noise_elements(soup: bs4.BeautifulSoup) -> None:
    """Remove structural noise (nav, chrome, sidebars) from a BeautifulSoup tree in-place.

    Uses extract() rather than decompose() so that child nodes already held in
    a pre-built find_all() list remain accessible without AttributeErrors.
    Skips tags that have already been detached (parent is None).
    """
    for tag in soup.find_all(NOISE_SEMANTIC_TAGS):
        if tag.parent is not None:
            tag.extract()

    for tag in soup.find_all(attrs={"role": True}):
        if tag.parent is None:
            continue
        role_value = tag.get("role", "")
        roles = role_value.split() if isinstance(role_value, str) else []
        if any(r in NOISE_ARIA_ROLES for r in roles):
            tag.extract()

    noise_pattern = re.compile(
        "|".join(re.escape(p) for p in NOISE_CLASS_PATTERNS), re.IGNORECASE
    )
    for tag in soup.find_all(True):
        if tag.parent is None or tag.name in _STRUCTURAL_TAGS:
            continue
        # Match against each class token individually to avoid false positives
        # on compound feature-flag class names (e.g. "vector-feature-menu-pinned").
        classes = tag.get("class", [])
        tag_id = tag.get("id", "") or ""
        class_hit = any(noise_pattern.search(cls) for cls in classes)
        id_hit = noise_pattern.search(tag_id)
        if class_hit or id_hit:
            tag.extract()


def web_html_cleanup(
    page_content: str | bs4.BeautifulSoup,
    mintlify_cleanup_enabled: bool = True,
    additional_element_types_to_discard: list[str] | None = None,
) -> ParsedHTML:
    if isinstance(page_content, str):
        soup = bs4.BeautifulSoup(page_content, "lxml")
    else:
        soup = page_content

    title_tag = soup.find("title")
    title = None
    if title_tag and title_tag.text:
        title = title_tag.text
        title_tag.extract()

    # Heuristics based cleaning of elements based on css classes
    unwanted_classes = copy(WEB_CONNECTOR_IGNORED_CLASSES)
    if mintlify_cleanup_enabled:
        unwanted_classes.extend(MINTLIFY_UNWANTED)
    for undesired_element in unwanted_classes:
        [
            tag.extract()
            for tag in soup.find_all(
                class_=lambda x: x and undesired_element in x.split()
            )
        ]

    for undesired_tag in WEB_CONNECTOR_IGNORED_ELEMENTS:
        [tag.extract() for tag in soup.find_all(undesired_tag)]

    for non_content_tag in NON_CONTENT_TAGS:
        [tag.extract() for tag in soup.find_all(non_content_tag)]

    if additional_element_types_to_discard:
        for undesired_tag in additional_element_types_to_discard:
            [tag.extract() for tag in soup.find_all(undesired_tag)]

    page_text = ""

    if PARSE_WITH_TRAFILATURA:
        # Pass the full minimally-cleaned document to trafilatura so its own
        # content-extraction algorithms can work on complete page context.
        # Applying our noise filters first degrades trafilatura's heuristics.
        try:
            page_text = parse_html_with_trafilatura(str(soup))
            if not page_text:
                raise ValueError("Empty content returned by trafilatura.")
        except Exception as e:
            logger.warning("Trafilatura parsing failed: %s. Falling back on bs4.", e)
            _remove_noise_elements(soup)
            content_root = _select_content_root(soup)
            page_text = format_document_soup(content_root)
    else:
        _remove_noise_elements(soup)
        content_root = _select_content_root(soup)
        page_text = format_document_soup(content_root)

    # 200B is ZeroWidthSpace which we don't care for
    cleaned_text = page_text.replace("\u200b", "")

    return ParsedHTML(title=title, cleaned_text=cleaned_text)
