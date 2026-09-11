"""Core and control-flow component templates.

Field names and defaults are taken **verbatim** from
``agents/graphs/schemas.py`` wherever an existing schema declares them, so the
canvas and the classic form produce the same agent. ``test_core_templates.py``
asserts this against the live schema registry rather than hardcoded strings.

Palette definition: ``.tmp/flow-canvas-design.md`` sections 7.1 and 7.2.
"""

from __future__ import annotations

from agents.graphs.schemas import GraphSchemaType, get_schema
from domain.flows.comparison import CONDITION_OPERATORS
from domain.flows.guardrails import GUARDRAIL_NAMES
from domain.flows.output_schema import SCHEMA_TYPES
from domain.flows.registry import ComponentRegistry
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FieldType,
    Handle,
    InputField,
    PortType,
    ShowWhen,
    TableColumn,
)

CATEGORY_CORE = "core"
CATEGORY_MODELS = "models"
CATEGORY_AGENTS = "agents"
CATEGORY_LOGIC = "logic"


def _schema_default(schema_type: GraphSchemaType, field: str) -> str | int | None:
    """Read a field default from the live graph-schema registry.

    Reading rather than copying keeps the canvas and the classic form in sync;
    if a schema default changes, the template follows it automatically.
    """
    schema = get_schema(schema_type)
    if schema is None:
        return None
    return schema.config_schema.get(field, {}).get("default")


def _system_prompt_field(schema_type: GraphSchemaType) -> InputField:
    return InputField(
        type=FieldType.PROMPT,
        display_name="System prompt",
        required=True,
        value=_schema_default(schema_type, "system_prompt"),
        info="Instructions that shape how this agent behaves.",
    )


def tool_mode_fields() -> dict[str, InputField]:
    """The two fields every tool-capable component declares.

    Shared rather than repeated so the copy, the defaults and the visibility
    rule cannot drift between the components that offer tool mode.
    """
    return {
        "tool_mode": InputField(
            type=FieldType.BOOL,
            display_name="Use as agent tool",
            required=False,
            value=False,
            info=(
                "Hand this component to an agent instead of running it as a "
                "flow step. Wire its Tool output into the agent's Tools port."
            ),
        ),
        "tool_name": InputField(
            type=FieldType.STR,
            display_name="Tool name",
            required=False,
            value="",
            advanced=True,
            show_when=ShowWhen(field="tool_mode", equals=True),
            info="The name the model sees. Blank derives one from the node.",
        ),
    }


def tool_output_handle() -> Handle:
    """The Tool port, present only in tool mode."""
    return Handle(
        name="tool",
        types=[PortType.TOOLS],
        show_when=ShowWhen(field="tool_mode", equals=True),
    )


#: The components a flow author may hand to an agent as a tool (decision 6.2).
#: Control-flow and boundary components are absent on purpose: an agent
#: calling a "loop tool" means nothing. A component missing from this set does
#: not have the capability — it is not a partial version of one.
TOOL_MODE_TYPES: frozenset[str] = frozenset(
    {
        "WebSearch",
        "FetchWebpage",
        "ContentCrawl",
        "DocumentSearch",
        "KnowledgeBase",
        "GraphSearch",
        "GraphEntitySearch",
        "GraphNeighborhood",
        "GraphStats",
        "Operations",
        "SplitText",
        "TypeConverter",
        "Parser",
        "StructuredOutput",
        "RunFlow",
        # BatchRun is absent on purpose: it needs a table wired to its Table
        # port, which a model calling a tool has no way to supply.
    }
)


def apply_tool_mode(template: ComponentTemplate) -> ComponentTemplate:
    """Enable tool mode on ``template`` if its type is in TOOL_MODE_TYPES.

    Called from each registrar so the capability list lives in one place
    rather than as a flag repeated across four template modules.
    """
    if template.type not in TOOL_MODE_TYPES:
        return template
    return with_tool_mode(template)


def with_tool_mode(template: ComponentTemplate) -> ComponentTemplate:
    """Return ``template`` with agent-tool mode enabled.

    One helper rather than the same three edits in fourteen templates: the
    copy, the defaults and the visibility rule cannot drift apart, and a
    component joins the capability by being wrapped here.

    An existing output handle gains a "hide me in tool mode" rule only if it
    does not already carry one — ``ShowWhen`` tests a single field, and a
    handle whose visibility already depends on another field (Data
    Operations' three typed outputs) keeps that rule. Wiring such a port on a
    tool-mode node is caught by the validator instead.
    """
    outputs = []
    for handle in template.handles.outputs:
        if handle.show_when is None:
            handle = handle.model_copy(
                update={"show_when": ShowWhen(field="tool_mode", equals=False)}
            )
        outputs.append(handle)
    outputs.append(tool_output_handle())

    return template.model_copy(
        update={
            "tool_mode_field": "tool_mode",
            "inputs": {**tool_mode_fields(), **template.inputs},
            "handles": template.handles.model_copy(update={"outputs": outputs}),
        }
    )


def _message_in() -> Handle:
    return Handle(name="input", types=[PortType.MESSAGE])


def _message_out() -> Handle:
    return Handle(name="output", types=[PortType.MESSAGE])


def _model_in() -> Handle:
    return Handle(name="model", types=[PortType.MODEL])


def _tools_in() -> Handle:
    return Handle(name="tools", types=[PortType.TOOLS])


def _memory_in() -> Handle:
    return Handle(name="memory", types=[PortType.MEMORY])


# ---------------------------------------------------------------------------
# Core — input / output
# ---------------------------------------------------------------------------


def _chat_input() -> ComponentTemplate:
    return ComponentTemplate(
        type="ChatInput",
        category=CATEGORY_CORE,
        display_name="Chat Input",
        description="Where the user's message enters the flow.",
        icon="SvgBubbleText",
        kind=ComponentKind.EXECUTION,
        handles=ComponentHandles(
            outputs=[Handle(name="message", types=[PortType.MESSAGE])],
        ),
    )


def _chat_output() -> ComponentTemplate:
    return ComponentTemplate(
        type="ChatOutput",
        category=CATEGORY_CORE,
        display_name="Chat Output",
        description="Where the flow's answer leaves for the user.",
        icon="SvgArrowWallRight",
        kind=ComponentKind.EXECUTION,
        handles=ComponentHandles(
            inputs=[Handle(name="message", types=[PortType.MESSAGE])],
        ),
    )


def _text_input() -> ComponentTemplate:
    return ComponentTemplate(
        type="TextInput",
        category=CATEGORY_CORE,
        display_name="Text Input",
        description="A fixed piece of text supplied by the flow author.",
        icon="SvgTextLines",
        kind=ComponentKind.EXECUTION,
        inputs={
            "text": InputField(
                type=FieldType.PROMPT,
                display_name="Text",
                required=True,
                value="",
            ),
        },
        handles=ComponentHandles(
            outputs=[Handle(name="text", types=[PortType.MESSAGE])],
        ),
    )


def _file_input() -> ComponentTemplate:
    return ComponentTemplate(
        type="FileInput",
        category=CATEGORY_CORE,
        display_name="File Input",
        description="A file attached to the conversation.",
        icon="SvgFileText",
        kind=ComponentKind.EXECUTION,
        inputs={
            "file": InputField(
                type=FieldType.FILE,
                display_name="File",
                required=True,
            ),
        },
        handles=ComponentHandles(
            outputs=[Handle(name="data", types=[PortType.DATA])],
        ),
    )


def _prompt_template() -> ComponentTemplate:
    return ComponentTemplate(
        type="PromptTemplate",
        category=CATEGORY_CORE,
        display_name="Prompt Template",
        description="Builds a prompt string from variables supplied upstream.",
        icon="SvgFileBraces",
        kind=ComponentKind.EXECUTION,
        inputs={
            "template": InputField(
                type=FieldType.PROMPT,
                display_name="Template",
                required=True,
                value="",
                info="Reference upstream values with {variable} placeholders.",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="variables", types=[PortType.DATA, PortType.TEXT])],
            outputs=[Handle(name="text", types=[PortType.MESSAGE])],
        ),
    )


# ---------------------------------------------------------------------------
# Models — resource nodes, injected at build time
# ---------------------------------------------------------------------------


def _llm_model() -> ComponentTemplate:
    return ComponentTemplate(
        type="LLMModel",
        category=CATEGORY_MODELS,
        display_name="LLM Model",
        description="A model from a configured provider.",
        icon="SvgCpu",
        kind=ComponentKind.RESOURCE,
        inputs={
            "provider": InputField(
                type=FieldType.OPTIONS,
                display_name="Provider",
                required=True,
                options_source="llm.providers",
            ),
            "model": InputField(
                type=FieldType.OPTIONS,
                display_name="Model",
                required=True,
                options_source="llm.models",
                depends_on=["provider"],
            ),
            "temperature": InputField(
                type=FieldType.SLIDER,
                display_name="Temperature",
                value=0.7,
                min=0,
                max=2,
                step=0.1,
            ),
            "max_tokens": InputField(
                type=FieldType.INT,
                display_name="Max tokens",
                advanced=True,
            ),
        },
        handles=ComponentHandles(
            outputs=[Handle(name="model", types=[PortType.MODEL])],
        ),
    )


def _ollama_model() -> ComponentTemplate:
    return ComponentTemplate(
        type="OllamaModel",
        category=CATEGORY_MODELS,
        display_name="Ollama Model",
        description="A model served by the platform's Ollama runtime.",
        icon="SvgServer",
        kind=ComponentKind.RESOURCE,
        inputs={
            "model": InputField(
                type=FieldType.OPTIONS,
                display_name="Model",
                required=True,
                options_source="ollama.models",
            ),
            "temperature": InputField(
                type=FieldType.SLIDER,
                display_name="Temperature",
                value=0.7,
                min=0,
                max=2,
                step=0.1,
            ),
        },
        handles=ComponentHandles(
            outputs=[Handle(name="model", types=[PortType.MODEL])],
        ),
    )


# ---------------------------------------------------------------------------
# Agents — one per existing graph schema
# ---------------------------------------------------------------------------


def _chatbot() -> ComponentTemplate:
    return ComponentTemplate(
        type="Chatbot",
        category=CATEGORY_AGENTS,
        display_name="Chatbot",
        description="Standard conversational AI chatbot with memory.",
        icon="SvgBubbleText",
        kind=ComponentKind.EXECUTION,
        inputs={"system_prompt": _system_prompt_field(GraphSchemaType.ZERO_SHOT)},
        handles=ComponentHandles(
            inputs=[_message_in(), _model_in(), _memory_in()],
            outputs=[_message_out()],
        ),
    )


def _zero_shot_agent() -> ComponentTemplate:
    return ComponentTemplate(
        type="ZeroShotAgent",
        category=CATEGORY_AGENTS,
        display_name="Zero-Shot Agent",
        description="A single model call with a system prompt. No tools.",
        icon="SvgSparkle",
        kind=ComponentKind.EXECUTION,
        inputs={"system_prompt": _system_prompt_field(GraphSchemaType.ZERO_SHOT)},
        handles=ComponentHandles(
            inputs=[_message_in(), _model_in(), _memory_in()],
            outputs=[_message_out()],
        ),
    )


def _react_agent() -> ComponentTemplate:
    return ComponentTemplate(
        type="ReActAgent",
        category=CATEGORY_AGENTS,
        display_name="ReAct Agent",
        description="Reasons and calls tools until it can answer.",
        icon="SvgWorkflow",
        kind=ComponentKind.EXECUTION,
        inputs={"system_prompt": _system_prompt_field(GraphSchemaType.REACT)},
        handles=ComponentHandles(
            inputs=[_message_in(), _model_in(), _tools_in(), _memory_in()],
            outputs=[_message_out()],
        ),
    )


def _plan_execute_agent() -> ComponentTemplate:
    return ComponentTemplate(
        type="PlanExecuteAgent",
        category=CATEGORY_AGENTS,
        display_name="Plan & Execute Agent",
        description="Plans an approach first, then executes it step by step.",
        icon="SvgCheckSquare",
        kind=ComponentKind.EXECUTION,
        inputs={"system_prompt": _system_prompt_field(GraphSchemaType.PLAN_EXECUTE)},
        handles=ComponentHandles(
            inputs=[_message_in(), _model_in(), _tools_in(), _memory_in()],
            outputs=[_message_out()],
        ),
    )


def _self_reflect_agent() -> ComponentTemplate:
    return ComponentTemplate(
        type="SelfReflectAgent",
        category=CATEGORY_AGENTS,
        display_name="Self-Reflect Agent",
        description="Drafts an answer, critiques it, and revises.",
        icon="SvgArrowExchange",
        kind=ComponentKind.EXECUTION,
        inputs={
            "system_prompt": _system_prompt_field(GraphSchemaType.SELF_REFLECT),
            "reflection_prompt": InputField(
                type=FieldType.PROMPT,
                display_name="Reflection prompt",
                required=True,
                value=_schema_default(GraphSchemaType.SELF_REFLECT, "reflection_prompt"),
            ),
            "max_iterations": InputField(
                type=FieldType.INT,
                display_name="Max revisions",
                value=_schema_default(GraphSchemaType.SELF_REFLECT, "max_iterations"),
                advanced=True,
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in(), _model_in(), _memory_in()],
            outputs=[_message_out()],
        ),
    )


# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------


def _router() -> ComponentTemplate:
    return ComponentTemplate(
        type="Router",
        category=CATEGORY_LOGIC,
        display_name="Router",
        description="Sends the conversation down one of several branches.",
        icon="SvgBranch",
        template_version=2,
        kind=ComponentKind.EXECUTION,
        inputs={
            "routes": InputField(
                type=FieldType.TABLE,
                display_name="Routes",
                required=True,
                info=(
                    "Each row compares a Source (a Set Variable name, or blank "
                    "for the latest message) against Match text with an "
                    "Operator, and selects the Route branch on the first match."
                ),
                columns=[
                    TableColumn(name="source", display_name="Source"),
                    TableColumn(
                        name="operator",
                        display_name="Operator",
                        type=FieldType.OPTIONS,
                        options=list(CONDITION_OPERATORS),
                    ),
                    TableColumn(name="match_text", display_name="Match text"),
                    TableColumn(name="route", display_name="Route"),
                ],
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in()],
            outputs=[
                # Message, like If-Else's true/false ports: the conversation
                # flows on down the chosen branch. (Trigger would make every
                # route -> agent edge a type mismatch.)
                Handle(
                    name="routes",
                    types=[PortType.MESSAGE],
                    expands_from="routes",
                    expands_label_key="route",
                )
            ],
        ),
    )


def _loop() -> ComponentTemplate:
    """Langflow's Loop: a foreach over a collection. Each item goes down the
    ``item`` branch; when the collection is exhausted the aggregated results
    leave via ``done``. Sequential, exactly like Langflow's LoopComponent —
    the graph re-enters the node once per item.

    The pre-Phase-3 counter while-loop moved to the ``While`` type; a v1
    ``Loop`` node is renamed to ``While`` on read (migrate_spec)."""
    return ComponentTemplate(
        type="Loop",
        category=CATEGORY_LOGIC,
        display_name="Loop",
        description=(
            "Runs a branch once per item in a list, then sends the collected "
            "results down the Done branch."
        ),
        icon="SvgRefreshCw",
        template_version=2,
        kind=ComponentKind.EXECUTION,
        inputs={
            "items_source": InputField(
                type=FieldType.STR,
                display_name="Items",
                required=False,
                value="",
                info=(
                    "Wire a collection into the Items port, or name a Set "
                    "Variable holding a list here. With neither, the lines of "
                    "the latest message are iterated."
                ),
            ),
        },
        handles=ComponentHandles(
            inputs=[
                _message_in(),
                # Langflow's Loop takes its collection through a HandleInput
                # (DataFrame / Table / Data / Message). Same idea, in the types
                # we carry — this is what lets a search result be iterated.
                Handle(
                    name="items",
                    types=[PortType.DATA, PortType.DOCUMENTS, PortType.MESSAGE],
                    fallback_field="items_source",
                ),
            ],
            outputs=[
                # Data alongside Message: Langflow's item is a Data and its
                # done is a DataFrame. The structured value rides in scratch
                # under the node id; the message keeps the branch readable.
                Handle(name="item", types=[PortType.MESSAGE, PortType.DATA]),
                Handle(name="done", types=[PortType.MESSAGE, PortType.DATA]),
            ],
        ),
    )


def _while() -> ComponentTemplate:
    """A bounded counter loop: repeat a branch while an optional scratch key is
    truthy, up to Max iterations. Our own primitive — Langflow has no
    while-loop — so it does not take the ``Loop`` name (that is Langflow's
    foreach). A v1 ``Loop`` node migrates to this type."""
    return ComponentTemplate(
        type="While",
        category=CATEGORY_LOGIC,
        display_name="While",
        description="Repeats a branch while a condition holds or until the bound is hit.",
        icon="SvgRefreshCw",
        kind=ComponentKind.EXECUTION,
        inputs={
            "condition": InputField(
                type=FieldType.STR,
                display_name="Continue while",
                required=False,
                info=(
                    "Optional. The name of a scratch key; the loop repeats while "
                    "that key is truthy. Leave empty for a plain bounded loop that "
                    "runs up to Max iterations. For a content-driven loop, use a "
                    "ConditionalRouter instead."
                ),
            ),
            # Required by design: an unbounded loop is the canvas's deadlock risk.
            "max_iterations": InputField(
                type=FieldType.INT,
                display_name="Max iterations",
                required=True,
                value=5,
                info="Hard bound. The loop exits here even if the condition still holds.",
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in()],
            outputs=[
                Handle(name="continue", types=[PortType.MESSAGE]),
                Handle(name="exit", types=[PortType.MESSAGE]),
            ],
        ),
    )


def _merge() -> ComponentTemplate:
    return ComponentTemplate(
        type="Merge",
        category=CATEGORY_LOGIC,
        display_name="Merge",
        description="Joins several branches back into one.",
        icon="SvgLinkedDots",
        kind=ComponentKind.EXECUTION,
        inputs={
            "strategy": InputField(
                type=FieldType.OPTIONS,
                display_name="Strategy",
                required=True,
                options=["concat", "first", "last"],
                value="concat",
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in()],
            outputs=[_message_out()],
        ),
    )


def _conditional_router() -> ComponentTemplate:
    return ComponentTemplate(
        type="ConditionalRouter",
        category=CATEGORY_LOGIC,
        display_name="If-Else",
        description=(
            "Compares the latest message against a fixed rule and sends the "
            "conversation down the true or the false branch. Wire a branch back "
            "upstream for a condition-driven loop."
        ),
        icon="SvgBranch",
        kind=ComponentKind.EXECUTION,
        inputs={
            "operator": InputField(
                type=FieldType.OPTIONS,
                display_name="Operator",
                required=True,
                options=list(CONDITION_OPERATORS),
                value="contains",
                info=(
                    "How the incoming message is compared with Match text. "
                    "'regex' is anchored at the start (Python re.match) and "
                    "ignores Case sensitive; the numeric operators coerce both "
                    "sides to numbers."
                ),
            ),
            "match_text": InputField(
                type=FieldType.STR,
                display_name="Match text",
                required=True,
                value="",
                info="The text (or number, or regex pattern) compared against.",
            ),
            "input_source": InputField(
                type=FieldType.STR,
                display_name="Compare",
                required=False,
                value="",
                advanced=True,
                info=(
                    "A Set Variable name to compare instead of the latest "
                    "message. Leave empty to compare the latest message."
                ),
            ),
            "true_case_message": InputField(
                type=FieldType.STR,
                display_name="True branch message",
                required=False,
                value="",
                advanced=True,
                info="Sent down the true branch instead of the input. Blank forwards the input.",
            ),
            "false_case_message": InputField(
                type=FieldType.STR,
                display_name="False branch message",
                required=False,
                value="",
                advanced=True,
                info="Sent down the false branch instead of the input. Blank forwards the input.",
            ),
            "case_sensitive": InputField(
                type=FieldType.BOOL,
                display_name="Case sensitive",
                value=True,
                advanced=True,
                show_when=ShowWhen(field="operator", not_equals="regex"),
                info="Ignored for the 'regex' operator.",
            ),
            "strip_match": InputField(
                type=FieldType.BOOL,
                display_name="Strip match text",
                value=False,
                advanced=True,
                info=(
                    "Remove Match text from the message before it continues down "
                    "either branch. Turn this on when Match text is a completion "
                    "marker the user should not see (e.g. a loop's done signal)."
                ),
            ),
            # An unbounded cycle is the canvas's deadlock risk (R2), so a
            # positive bound is mandatory here exactly as it is on Loop.
            "max_iterations": InputField(
                type=FieldType.INT,
                display_name="Max iterations",
                required=True,
                value=10,
                info=(
                    "Hard bound on how many times this node may run on one turn. "
                    "Once reached, the Default route is taken and the cycle stops."
                ),
            ),
            "default_route": InputField(
                type=FieldType.OPTIONS,
                display_name="Default route",
                required=True,
                options=["true_result", "false_result"],
                value="false_result",
                advanced=True,
                info=(
                    "The branch taken once Max iterations is hit. In a loop this "
                    "must be the branch that leaves the loop."
                ),
            ),
        },
        handles=ComponentHandles(
            # Langflow's input_text is a required wired port and the two case
            # messages are MessageInputs — an inline value and a port at once.
            # Same shape here; the wired port always wins over the field.
            inputs=[
                _message_in(),
                Handle(
                    name="input_text",
                    types=[PortType.MESSAGE, PortType.DATA, PortType.TEXT],
                    fallback_field="input_source",
                ),
                Handle(
                    name="true_case_message",
                    types=[PortType.MESSAGE],
                    fallback_field="true_case_message",
                ),
                Handle(
                    name="false_case_message",
                    types=[PortType.MESSAGE],
                    fallback_field="false_case_message",
                ),
            ],
            outputs=[
                Handle(name="true_result", types=[PortType.MESSAGE]),
                Handle(name="false_result", types=[PortType.MESSAGE]),
            ],
        ),
    )


def _smart_router() -> ComponentTemplate:
    return ComponentTemplate(
        type="SmartRouter",
        category=CATEGORY_LOGIC,
        display_name="Smart Router",
        description=(
            "Uses an LLM to sort the latest message into one of the categories "
            "you define, then sends the conversation down that branch."
        ),
        icon="SvgSparkle",
        template_version=2,
        kind=ComponentKind.EXECUTION,
        inputs={
            "routes": InputField(
                type=FieldType.TABLE,
                display_name="Categories",
                required=True,
                info=(
                    "One row per category: its name (the branch label), a "
                    "description the LLM uses to choose, and an optional "
                    "message sent down that branch instead of the original "
                    "input."
                ),
                columns=[
                    TableColumn(name="route_category", display_name="Category"),
                    TableColumn(name="route_description", display_name="Description"),
                    TableColumn(name="output_value", display_name="Output value"),
                ],
            ),
            "message": InputField(
                type=FieldType.STR,
                display_name="Override output",
                required=False,
                value="",
                advanced=True,
                info=(
                    "When filled, this replaces the branch message for every "
                    "category, ignoring each row's own value."
                ),
            ),
            "enable_else_output": InputField(
                type=FieldType.BOOL,
                display_name="Enable Else output",
                value=False,
                advanced=True,
                info=(
                    "Adds an 'else' branch taken when the message fits no "
                    "category. When off, an unmatched category is an error."
                ),
            ),
            "custom_prompt": InputField(
                type=FieldType.PROMPT,
                display_name="Additional instructions",
                required=False,
                value="",
                advanced=True,
                info=(
                    "Extra guidance appended to the built-in categorisation "
                    "prompt — it does not replace it. Use {input_text} for the "
                    "message and {routes} for the category list."
                ),
            ),
        },
        handles=ComponentHandles(
            inputs=[
                _message_in(),
                _model_in(),
                # Langflow's Override Output is a MessageInput: an inline value
                # and a port at once. Same shape here — the port wins.
                Handle(
                    name="message",
                    types=[PortType.MESSAGE],
                    fallback_field="message",
                ),
            ],
            outputs=[
                Handle(
                    name="routes",
                    types=[PortType.MESSAGE],
                    expands_from="routes",
                    expands_label_key="route_category",
                ),
                Handle(
                    name="else",
                    types=[PortType.MESSAGE],
                    show_when=ShowWhen(field="enable_else_output", equals=True),
                ),
            ],
        ),
    )


def _guardrails() -> ComponentTemplate:
    """Langflow's Guardrails: check a piece of text against LLM-backed rules and
    send it down the Pass or the Fail branch.

    The behaviour is Langflow's, including the parts tuned against false
    positives: the model is told to allow the text unless it is certain, an
    unreadable reply counts as a pass, and only Jailbreak / Prompt Injection get
    the cheap pattern pre-filter. It is a filter, not a proof — the ``info``
    copy says so, because a node called "Guardrails" that quietly blocked more
    than Langflow's would be a different component wearing the same name.

    Langflow's API Key field has no counterpart: credentials live on the wired
    Model resource here, the same as every other model-using component.
    """
    return ComponentTemplate(
        type="Guardrails",
        category=CATEGORY_LOGIC,
        display_name="Guardrails",
        description=(
            "Checks text against safety and privacy rules with an LLM, then "
            "sends it down the Pass or the Fail branch."
        ),
        icon="SvgShield",
        kind=ComponentKind.EXECUTION,
        inputs={
            "enabled_guardrails": InputField(
                type=FieldType.MULTISELECT,
                display_name="Guardrails",
                required=True,
                options=list(GUARDRAIL_NAMES),
                value=["PII", "Tokens/Passwords", "Jailbreak"],
                info=(
                    "Checks run in this order and stop at the first failure, so "
                    "each one you add costs a model call only while everything "
                    "before it passes. Detection is advisory: the model is "
                    "instructed to allow text unless it is certain."
                ),
            ),
            "input_source": InputField(
                type=FieldType.STR,
                display_name="Validate",
                required=False,
                value="",
                advanced=True,
                info=(
                    "A Set Variable name to validate instead of the latest "
                    "message. Leave empty to validate the latest message."
                ),
            ),
            "enable_custom_guardrail": InputField(
                type=FieldType.BOOL,
                display_name="Enable custom guardrail",
                value=False,
                advanced=True,
                info="Adds one extra check described in your own words.",
            ),
            "custom_guardrail_explanation": InputField(
                type=FieldType.PROMPT,
                display_name="Custom guardrail description",
                required=False,
                value="",
                advanced=True,
                show_when=ShowWhen(field="enable_custom_guardrail", equals=True),
                info=(
                    "What the extra check should look for, e.g. 'Detect if the "
                    "input contains medical or health information'. Be specific: "
                    "this description is what the model is asked about."
                ),
            ),
            "heuristic_threshold": InputField(
                type=FieldType.SLIDER,
                display_name="Pattern detection threshold",
                value=0.7,
                min=0,
                max=1,
                step=0.1,
                advanced=True,
                info=(
                    "Jailbreak and Prompt Injection are pattern-scored before "
                    "any model call; text scoring at or above this fails "
                    "immediately. Lower is stricter, higher sends more cases to "
                    "the model. The other checks always call the model."
                ),
            ),
        },
        handles=ComponentHandles(
            inputs=[
                _message_in(),
                _model_in(),
                Handle(
                    name="input_text",
                    types=[PortType.MESSAGE, PortType.TEXT, PortType.DATA],
                    fallback_field="input_source",
                ),
            ],
            outputs=[
                # Pass forwards the validated text; Fail carries the fixed
                # justification, never the model's own wording of it.
                Handle(name="pass_result", types=[PortType.MESSAGE]),
                Handle(name="fail_result", types=[PortType.MESSAGE]),
                # Langflow never stops Result Data, so this branch runs on both
                # outcomes — wire it for an audit trail of every verdict.
                Handle(name="data_result", types=[PortType.DATA]),
            ],
        ),
    )


def _human_input() -> ComponentTemplate:
    """Langflow's Human Input: pause the flow, show a prompt and a set of
    actions, and continue down the branch of whichever action the person
    picks. No timeout — the run waits in the thread until a reply arrives.

    The extra branch is ``unmatched``, not Langflow's ``fallback``. Langflow's
    fallback is its *timeout* path; ours is taken when the answer matches no
    action — a case Langflow's button UI cannot produce, but ours can, because
    a person may type instead of pressing a button. Different job, different
    name; ``fallback`` stays reserved for a real timeout."""
    return ComponentTemplate(
        type="HumanInput",
        template_version=2,
        category=CATEGORY_LOGIC,
        display_name="Human Input",
        description=(
            "Pauses the flow and asks a person to choose an action; continues "
            "down that action's branch when they answer."
        ),
        icon="SvgUserManage",
        kind=ComponentKind.EXECUTION,
        inputs={
            "prompt": InputField(
                type=FieldType.PROMPT,
                display_name="Prompt",
                required=True,
                value="",
                info="The question shown to the person.",
            ),
            "decisions": InputField(
                type=FieldType.TABLE,
                display_name="Actions",
                required=True,
                info="One row per action: its label is the branch it continues down.",
                columns=[TableColumn(name="label", display_name="Action")],
            ),
            "enable_unmatched": InputField(
                type=FieldType.BOOL,
                display_name="Enable unmatched branch",
                value=False,
                advanced=True,
                info=(
                    "Adds an 'unmatched' branch taken when the answer matches "
                    "no action. When off, an unmatched answer is an error."
                ),
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in()],
            outputs=[
                Handle(
                    name="decisions",
                    types=[PortType.MESSAGE],
                    expands_from="decisions",
                    expands_label_key="label",
                ),
                Handle(
                    name="unmatched",
                    types=[PortType.MESSAGE],
                    show_when=ShowWhen(field="enable_unmatched", equals=True),
                ),
            ],
        ),
    )


def _structured_output() -> ComponentTemplate:
    """Langflow's Structured Output: an LLM forced to answer in a schema.

    The schema table is Langflow's, column for column. Its format instructions
    say "Extract ALL relevant instances", and its own model wraps the schema in
    a list to make that possible — so the stored value is always a list of
    objects, even when the text yields one.

    Langflow exposes two outputs, ``Data`` and ``DataFrame``, which are the
    same result in two shapes. We carry one: the objects live in
    ``scratch[node.id]`` and the JSON leaves as a message, because there is no
    DataFrame port type here (adding one with no consumer would be a type
    system that describes nothing).
    """
    return ComponentTemplate(
        type="StructuredOutput",
        category=CATEGORY_LOGIC,
        display_name="Structured Output",
        description=("Uses a model to pull structured records out of text, in a shape you define."),
        icon="SvgBracketCurly",
        kind=ComponentKind.EXECUTION,
        inputs={
            "output_schema": InputField(
                type=FieldType.TABLE,
                display_name="Output schema",
                required=True,
                info=(
                    "One row per field to extract: its name, a description the "
                    "model reads to find it, its type, and whether it is a list."
                ),
                columns=[
                    TableColumn(name="name", display_name="Name"),
                    TableColumn(name="description", display_name="Description"),
                    TableColumn(
                        name="type",
                        display_name="Type",
                        type=FieldType.OPTIONS,
                        options=sorted(SCHEMA_TYPES),
                    ),
                    TableColumn(name="multiple", display_name="As list", type=FieldType.BOOL),
                ],
            ),
            "schema_name": InputField(
                type=FieldType.STR,
                display_name="Schema name",
                required=False,
                value="OutputModel",
                advanced=True,
                info="Names the shape in the prompt; helps the model understand it.",
            ),
            "system_prompt": InputField(
                type=FieldType.PROMPT,
                display_name="Format instructions",
                required=False,
                value="",
                advanced=True,
                info="Overrides the built-in extraction instructions. Blank uses them.",
            ),
            "input_source": InputField(
                type=FieldType.STR,
                display_name="Extract from",
                required=False,
                value="",
                advanced=True,
                info=(
                    "A Set Variable name to extract from instead of the latest "
                    "message. Leave empty to use the latest message."
                ),
            ),
        },
        handles=ComponentHandles(
            inputs=[
                _message_in(),
                _model_in(),
                Handle(
                    name="input_text",
                    types=[PortType.MESSAGE, PortType.DATA, PortType.TEXT],
                    fallback_field="input_source",
                ),
            ],
            outputs=[Handle(name="output", types=[PortType.MESSAGE, PortType.DATA])],
        ),
    )


def _run_flow() -> ComponentTemplate:
    """Langflow's Run Flow: execute another published flow as one node.

    Langflow derives dynamic fields and ports from the target's input/output
    vertices, because a Langflow flow can have any number of each. Ours
    cannot: the validator requires exactly one Chat Input and at least one
    Chat Output, so a sub-flow is always message-in / message-out. Same
    function, no dynamic ports needed.

    The target's *current published* version runs — there is deliberately no
    version field, so publishing a fix to a shared sub-flow fixes every caller
    at once (decision 5.3).

    Langflow marks ``SubFlow`` and ``FlowTool`` legacy with
    ``replacement = ["logic.RunFlow"]``; this is the one sanctioned door, and
    ``AgentRef``/``Supervisor`` keep their own ban (decision 5.5).
    """
    return ComponentTemplate(
        type="RunFlow",
        category=CATEGORY_LOGIC,
        display_name="Run Flow",
        description="Runs another published flow and passes its answer on.",
        icon="SvgWorkflow",
        kind=ComponentKind.EXECUTION,
        inputs={
            "flow_id": InputField(
                type=FieldType.OPTIONS,
                display_name="Flow",
                required=True,
                options_source="flows.published",
                info=(
                    "The flow to run. Its current published version is used, "
                    "so publishing a fix there updates every flow that calls it."
                ),
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in()],
            outputs=[_message_out()],
        ),
    )


def _set_variable() -> ComponentTemplate:
    return ComponentTemplate(
        type="SetVariable",
        category=CATEGORY_LOGIC,
        display_name="Set Variable",
        description=(
            "Stores a value under a name, so a later Prompt Template can read it as {name}."
        ),
        icon="SvgBracketCurly",
        kind=ComponentKind.EXECUTION,
        inputs={
            "name": InputField(
                type=FieldType.STR,
                display_name="Name",
                required=True,
                value="",
                info=(
                    "Letters, digits and underscores, starting with a letter. "
                    "This is the name you use as {name} in a Prompt Template."
                ),
            ),
            "value": InputField(
                type=FieldType.STR,
                display_name="Value",
                required=False,
                value="",
                info="Leave empty to store the latest message's text.",
            ),
            "append": InputField(
                type=FieldType.BOOL,
                display_name="Append",
                value=False,
                advanced=True,
                info="Append to a list under this name instead of replacing it.",
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in()],
            outputs=[_message_out()],
        ),
    )


CORE_TEMPLATE_FACTORIES = (
    _chat_input,
    _chat_output,
    _text_input,
    _file_input,
    _prompt_template,
    _llm_model,
    _ollama_model,
    _chatbot,
    _zero_shot_agent,
    _react_agent,
    _plan_execute_agent,
    _self_reflect_agent,
    _router,
    _loop,
    _while,
    _merge,
    _conditional_router,
    _smart_router,
    _guardrails,
    _human_input,
    _run_flow,
    _set_variable,
    _structured_output,
)


def register_core_templates(registry: ComponentRegistry) -> None:
    """Register every Core and control-flow template into ``registry``."""
    for factory in CORE_TEMPLATE_FACTORIES:
        registry.register(apply_tool_mode(factory()))
