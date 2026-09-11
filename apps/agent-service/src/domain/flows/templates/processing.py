"""Processing component templates — Langflow's data family.

Three components, all non-legacy in Langflow 1.11.2:

- ``Operations`` ("Data Operations") — 30 operations over Text, JSON and Table.
- ``SplitText`` — chunk text.
- ``TypeConverter`` ("Type Convert") — Message <-> JSON <-> Table.

Langflow's vocabulary: its ``Data`` type is displayed as **JSON** and its
``DataFrame`` as **Table**. The field names below are Langflow's own, so a
flow authored against its documentation reads the same here.

One deliberate difference in shape, none in behaviour: Langflow splits the
operation picker with an ``input_type`` tab and swaps the options with
``update_build_config``. Its dispatch is by operation name alone and the
three families share no name, so a single ``operation`` field with all thirty
options is functionally identical — and it works with the declarative
``show_when`` machinery instead of a server round-trip per keystroke.
"""

from __future__ import annotations

from domain.flows.data_ops import (
    ALL_OPERATIONS,
    CASE_CONVERTERS,
    CONVERT_OUTPUT_TYPES,
    DATA_OUTPUT_OPERATIONS,
    DATAFRAME_OUTPUT_OPERATIONS,
    FILTER_OPERATORS,
    KEEP_SEPARATOR_CHOICES,
    MERGE_TYPES,
    MESSAGE_OUTPUT_OPERATIONS,
    PARSER_MODES,
    STRIP_MODES,
    TEXT_OPERATION_ORDER,
)
from domain.flows.registry import ComponentRegistry
from domain.flows.templates.core import _model_in, apply_tool_mode
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FieldType,
    Handle,
    InputField,
    PortType,
    ShowWhen,
)

CATEGORY_PROCESSING = "processing"


def _when(*operations: str) -> ShowWhen:
    """Show this field only for these operations."""
    return ShowWhen(field="operation", one_of=list(operations))


def _field(
    field_type: FieldType,
    display_name: str,
    operations: tuple[str, ...],
    *,
    value=None,
    options=None,
    info: str | None = None,
) -> InputField:
    return InputField(
        type=field_type,
        display_name=display_name,
        required=False,
        value=value,
        options=list(options) if options else None,
        info=info,
        show_when=_when(*operations),
    )


def _operations() -> ComponentTemplate:
    return ComponentTemplate(
        type="Operations",
        category=CATEGORY_PROCESSING,
        display_name="Data Operations",
        description="Perform operations on Text, JSON, and Tables from a single component.",
        icon="SvgSparkle",
        kind=ComponentKind.EXECUTION,
        inputs={
            "operation": InputField(
                type=FieldType.OPTIONS,
                display_name="Operation",
                required=True,
                options=list(ALL_OPERATIONS),
                info=(
                    "The operation to perform. The fields it needs, and the "
                    "output it produces, appear once you choose one."
                ),
            ),
            # -- main inputs ------------------------------------------------
            "text_input": InputField(
                type=FieldType.PROMPT,
                display_name="Text",
                required=False,
                value="",
                info="The input text to process. A wired Text port overrides it.",
                show_when=_when(*TEXT_OPERATION_ORDER),
            ),
            # -- JSON operations --------------------------------------------
            "select_keys_input": _field(
                FieldType.JSON,
                "Select Keys",
                ("Select Keys",),
                value=[],
                info="Top-level keys to keep, as a list.",
            ),
            "append_update_data": _field(
                FieldType.JSON,
                "Append or Update",
                ("Append or Update",),
                value={"key": "value"},
                info="Key/value pairs to write at the top level.",
            ),
            "remove_keys_input": _field(
                FieldType.JSON,
                "Remove Keys",
                ("Remove Keys",),
                value=[],
                info="Keys to remove, at every depth.",
            ),
            "rename_keys_input": _field(
                FieldType.JSON,
                "Rename Keys",
                ("Rename Keys",),
                value={"old_key": "new_key"},
                info="Old-to-new key names, applied at every depth.",
            ),
            "selected_key": _field(
                FieldType.STR,
                "Select Path",
                ("Path Selection",),
                value="",
                info="A jq path, for example .user.name",
            ),
            "query": _field(
                FieldType.STR,
                "JQ Expression",
                ("JQ Expression",),
                value="",
                info="A jq program run against the JSON.",
            ),
            # -- Table operations -------------------------------------------
            "column_name": _field(
                FieldType.STR,
                "Column Name",
                (
                    "Filter",
                    "Sort",
                    "Drop Column",
                    "Rename Column",
                    "Replace Value",
                    "Drop Duplicates",
                ),
                value="",
            ),
            "filter_value": _field(FieldType.STR, "Filter Value", ("Filter",), value=""),
            "filter_operator": _field(
                FieldType.OPTIONS,
                "Filter Operator",
                ("Filter",),
                value="equals",
                options=FILTER_OPERATORS,
            ),
            "ascending": _field(FieldType.BOOL, "Sort Ascending", ("Sort",), value=True),
            "new_column_name": _field(
                FieldType.STR,
                "New Column Name",
                ("Rename Column", "Add Column"),
                value="",
            ),
            "new_column_value": _field(
                FieldType.STR,
                "New Column Value",
                ("Add Column",),
                value="",
            ),
            "columns_to_select": _field(
                FieldType.JSON,
                "Columns to Select",
                ("Select Columns",),
                value=[],
            ),
            "num_rows": _field(FieldType.INT, "Number of Rows", ("Head", "Tail"), value=5),
            "replace_value": _field(
                FieldType.STR,
                "Value to Replace",
                ("Replace Value",),
                value="",
            ),
            "replacement_value": _field(
                FieldType.STR,
                "Replacement Value",
                ("Replace Value",),
                value="",
            ),
            "merge_on_column": _field(
                FieldType.STR,
                "Merge On Column",
                ("Merge",),
                value="",
                info="Blank joins on the row index.",
            ),
            "merge_how": _field(
                FieldType.OPTIONS,
                "Merge Type",
                ("Merge",),
                value="inner",
                options=MERGE_TYPES,
            ),
            # -- Text operations --------------------------------------------
            "count_words": _field(FieldType.BOOL, "Count Words", ("Word Count",), value=True),
            "count_characters": _field(
                FieldType.BOOL,
                "Count Characters",
                ("Word Count",),
                value=True,
            ),
            "count_lines": _field(FieldType.BOOL, "Count Lines", ("Word Count",), value=True),
            "case_type": _field(
                FieldType.OPTIONS,
                "Case Type",
                ("Case Conversion",),
                value="lowercase",
                options=tuple(CASE_CONVERTERS),
            ),
            "search_pattern": _field(
                FieldType.STR,
                "Search Pattern",
                ("Text Replace",),
                value="",
            ),
            "replacement_text": _field(
                FieldType.STR,
                "Replacement Text",
                ("Text Replace",),
                value="",
            ),
            "use_regex": _field(FieldType.BOOL, "Use Regex", ("Text Replace",), value=False),
            "extract_pattern": _field(
                FieldType.STR,
                "Extract Pattern",
                ("Text Extract",),
                value="",
            ),
            "max_matches": _field(
                FieldType.INT,
                "Max Matches",
                ("Text Extract",),
                value=10,
                info="0 returns every match.",
            ),
            "head_characters": _field(
                FieldType.INT,
                "Characters from Start",
                ("Text Head",),
                value=100,
            ),
            "tail_characters": _field(
                FieldType.INT,
                "Characters from End",
                ("Text Tail",),
                value=100,
            ),
            "strip_mode": _field(
                FieldType.OPTIONS,
                "Strip Mode",
                ("Text Strip",),
                value="both",
                options=STRIP_MODES,
            ),
            "strip_characters": _field(
                FieldType.STR,
                "Characters to Strip",
                ("Text Strip",),
                value="",
                info="Blank strips whitespace.",
            ),
            "text_input_2": _field(
                FieldType.PROMPT,
                "Second Text Input",
                ("Text Join",),
                value="",
            ),
            "remove_extra_spaces": _field(
                FieldType.BOOL,
                "Remove Extra Spaces",
                ("Text Clean",),
                value=True,
            ),
            "remove_special_chars": _field(
                FieldType.BOOL,
                "Remove Special Characters",
                ("Text Clean",),
                value=False,
            ),
            "remove_empty_lines": _field(
                FieldType.BOOL,
                "Remove Empty Lines",
                ("Text Clean",),
                value=False,
            ),
            "table_separator": _field(
                FieldType.STR,
                "Table Separator",
                ("Text to DataFrame",),
                value="|",
            ),
            "has_header": _field(
                FieldType.BOOL,
                "Has Header",
                ("Text to DataFrame",),
                value=True,
            ),
        },
        handles=ComponentHandles(
            inputs=[
                Handle(name="input", types=[PortType.MESSAGE]),
                Handle(
                    name="text_input",
                    types=[PortType.MESSAGE, PortType.TEXT],
                    fallback_field="text_input",
                    show_when=_when(*TEXT_OPERATION_ORDER),
                ),
                Handle(
                    name="data",
                    types=[PortType.DATA],
                    show_when=ShowWhen(
                        field="operation", one_of=sorted(DATA_OUTPUT_OPERATIONS - {"Word Count"})
                    ),
                ),
                Handle(
                    name="df",
                    types=[PortType.DATAFRAME],
                    show_when=ShowWhen(
                        field="operation",
                        one_of=sorted(DATAFRAME_OUTPUT_OPERATIONS - {"Text to DataFrame"}),
                    ),
                ),
                Handle(
                    name="left_dataframe",
                    types=[PortType.DATAFRAME],
                    show_when=_when("Merge"),
                ),
                Handle(
                    name="right_dataframe",
                    types=[PortType.DATAFRAME],
                    show_when=_when("Merge"),
                ),
            ],
            outputs=[
                # Langflow swaps its single output with update_outputs; the same
                # routing here is three declared handles, each shown for the
                # operations that produce its type. Word Count and Text to
                # DataFrame leave the Text family's type on purpose — that is
                # Langflow's own routing, not a slip.
                Handle(
                    name="message_output",
                    types=[PortType.MESSAGE],
                    show_when=ShowWhen(field="operation", one_of=sorted(MESSAGE_OUTPUT_OPERATIONS)),
                ),
                Handle(
                    name="data_output",
                    types=[PortType.DATA],
                    show_when=ShowWhen(field="operation", one_of=sorted(DATA_OUTPUT_OPERATIONS)),
                ),
                Handle(
                    name="dataframe_output",
                    types=[PortType.DATAFRAME],
                    show_when=ShowWhen(
                        field="operation", one_of=sorted(DATAFRAME_OUTPUT_OPERATIONS)
                    ),
                ),
            ],
        ),
    )


def _split_text() -> ComponentTemplate:
    return ComponentTemplate(
        type="SplitText",
        category=CATEGORY_PROCESSING,
        display_name="Split Text",
        description="Split text into chunks based on specified criteria.",
        icon="SvgTextLines",
        kind=ComponentKind.EXECUTION,
        inputs={
            "chunk_size": InputField(
                type=FieldType.INT,
                display_name="Chunk Size",
                required=False,
                value=1000,
                info=(
                    "The maximum length of each chunk. Text is split by the "
                    "separator first, then chunks are merged up to this size."
                ),
            ),
            "chunk_overlap": InputField(
                type=FieldType.INT,
                display_name="Chunk Overlap",
                required=False,
                value=200,
                info="Number of characters to overlap between chunks.",
            ),
            "separator": InputField(
                type=FieldType.STR,
                display_name="Separator",
                required=False,
                value="\n",
                info="The character to split on. '/n' and '\\n' both mean a newline.",
            ),
            "text_key": InputField(
                type=FieldType.STR,
                display_name="Text Key",
                required=False,
                value="text",
                advanced=True,
                info="The column holding the text when a Table is wired in.",
            ),
            "keep_separator": InputField(
                type=FieldType.OPTIONS,
                display_name="Keep Separator",
                required=False,
                value="False",
                options=list(KEEP_SEPARATOR_CHOICES),
                advanced=True,
                info="Whether to keep the separator in the chunks, and where.",
            ),
        },
        handles=ComponentHandles(
            inputs=[
                Handle(name="input", types=[PortType.MESSAGE]),
                Handle(
                    name="data_inputs",
                    types=[PortType.MESSAGE, PortType.DATA, PortType.DATAFRAME],
                ),
            ],
            outputs=[Handle(name="dataframe", types=[PortType.DATAFRAME, PortType.DATA])],
        ),
    )


def _type_converter() -> ComponentTemplate:
    return ComponentTemplate(
        type="TypeConverter",
        category=CATEGORY_PROCESSING,
        display_name="Type Convert",
        description="Convert between different types (Message, JSON, Table)",
        icon="SvgArrowExchange",
        kind=ComponentKind.EXECUTION,
        inputs={
            "output_type": InputField(
                type=FieldType.OPTIONS,
                display_name="Output Type",
                required=True,
                value="Message",
                options=list(CONVERT_OUTPUT_TYPES),
                info="The type to convert to.",
            ),
            "auto_parse": InputField(
                type=FieldType.BOOL,
                display_name="Auto Parse",
                required=False,
                value=False,
                advanced=True,
                info="Detect and convert JSON/CSV strings automatically.",
            ),
        },
        handles=ComponentHandles(
            inputs=[
                Handle(name="input", types=[PortType.MESSAGE]),
                Handle(
                    name="input_data",
                    types=[PortType.MESSAGE, PortType.DATA, PortType.DATAFRAME],
                ),
            ],
            outputs=[
                Handle(
                    name="message_output",
                    types=[PortType.MESSAGE],
                    show_when=ShowWhen(field="output_type", equals="Message"),
                ),
                Handle(
                    name="data_output",
                    types=[PortType.DATA],
                    show_when=ShowWhen(field="output_type", equals="JSON"),
                ),
                Handle(
                    name="dataframe_output",
                    types=[PortType.DATAFRAME],
                    show_when=ShowWhen(field="output_type", equals="Table"),
                ),
            ],
        ),
    )


def _parser() -> ComponentTemplate:
    """Langflow's Parser: extract text using a template.

    The counterpart to Type Convert: that one changes a value's *type*, this
    one renders it into readable text. Two modes — a template per row/item, or
    Stringify, which renders the whole value (a table as markdown, JSON as a
    fenced block) and ignores the template.
    """
    return ComponentTemplate(
        type="Parser",
        category=CATEGORY_PROCESSING,
        display_name="Parser",
        description="Extracts text using a template.",
        icon="SvgFileBraces",
        kind=ComponentKind.EXECUTION,
        inputs={
            "mode": InputField(
                type=FieldType.OPTIONS,
                display_name="Mode",
                required=True,
                value="Parser",
                options=list(PARSER_MODES),
                info="Stringify renders the whole value instead of using a template.",
            ),
            "pattern": InputField(
                type=FieldType.PROMPT,
                display_name="Template",
                required=False,
                value="Text: {text}",
                show_when=ShowWhen(field="mode", equals="Parser"),
                info=(
                    "Use {curly brackets} to pull a table column or a JSON key, "
                    "for example: Name: {ad}, Score: {puan}"
                ),
            ),
            "sep": InputField(
                type=FieldType.STR,
                display_name="Separator",
                required=False,
                value="\n",
                advanced=True,
                info="Placed between rows or items.",
                show_when=ShowWhen(field="mode", equals="Parser"),
            ),
            "clean_data": InputField(
                type=FieldType.BOOL,
                display_name="Clean Data",
                required=False,
                value=True,
                advanced=True,
                show_when=ShowWhen(field="mode", equals="Stringify"),
                info="Drop a table's empty rows and collapse whitespace in its cells.",
            ),
        },
        handles=ComponentHandles(
            inputs=[
                Handle(name="input", types=[PortType.MESSAGE]),
                Handle(
                    name="input_data",
                    types=[PortType.DATA, PortType.DATAFRAME, PortType.MESSAGE],
                ),
            ],
            outputs=[Handle(name="parsed_text", types=[PortType.MESSAGE])],
        ),
    )


def _batch_run() -> ComponentTemplate:
    """Langflow's Batch Run: one model call per row of a table.

    The whole table goes to the model in a single batch and the answers come
    back as a new column beside the original rows — the one-node form of what
    a Loop plus an agent does by hand.
    """
    return ComponentTemplate(
        type="BatchRun",
        category=CATEGORY_PROCESSING,
        display_name="Batch Run",
        description=(
            "Runs a model on each row of a table column. With no column chosen, "
            "the whole row is sent."
        ),
        icon="SvgTextLines",
        kind=ComponentKind.EXECUTION,
        inputs={
            "column_name": InputField(
                type=FieldType.STR,
                display_name="Column Name",
                required=False,
                value="",
                info="The column to send. Blank sends the whole row.",
            ),
            "output_column_name": InputField(
                type=FieldType.STR,
                display_name="Output Column Name",
                required=False,
                value="model_response",
                info="Where the model's answer is stored.",
            ),
            "system_message": InputField(
                type=FieldType.PROMPT,
                display_name="Instructions",
                required=False,
                value="",
                info="Applied to every row.",
            ),
        },
        handles=ComponentHandles(
            inputs=[
                Handle(name="input", types=[PortType.MESSAGE]),
                _model_in(),
                Handle(name="df", types=[PortType.DATAFRAME]),
            ],
            outputs=[Handle(name="batch_results", types=[PortType.DATAFRAME, PortType.DATA])],
        ),
    )


PROCESSING_TEMPLATE_FACTORIES = (
    _operations,
    _split_text,
    _type_converter,
    _parser,
    _batch_run,
)


def register_processing_templates(registry: ComponentRegistry) -> None:
    """Register every processing template into ``registry``."""
    for factory in PROCESSING_TEMPLATE_FACTORIES:
        registry.register(apply_tool_mode(factory()))
