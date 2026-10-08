"""Flow processing node factories (StructuredOutput, Operations, SplitText, TypeConverter, Parser, BatchRun, ComponentTool)."""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from localization import t

from agents.graphs.flow.message_flow import (
    _extract_last_message_text,
    _resolve_port_value,
    derive_tool_name,
)
from agents.graphs.flow.state import FlowState, ResolvedResources
from agents.graphs.stage_report import capture_component_evidence, report_stage_output
from core.exceptions import FlowBuildError
from core.observability.logger import get_logger
from schemas.flows import FlowNode
from service.flow_model.registry import get_registry
from service.knowledge_evidence.references import EVIDENCE_ARTIFACT_KEY

logger = get_logger(__name__)

_DEFAULT_FORMAT_INSTRUCTIONS = (
    "You extract structured JSON objects from the text you are given, matching "
    "a predefined schema (types: str, int, float, bool, dict). "
    "Only use values that actually appear in the text. If a field's value is "
    "not in the text, set it to null — never copy the field's name or "
    "description as its value, and never invent a plausible value. "
    "Return exactly one object per distinct real-world record the text "
    "describes; if the text describes a single record, return a single object "
    "— do not split one record across several objects. "
    "If the text contains no extractable record, return an empty list. "
    "Always return valid JSON in the expected format."
)


_RETRY_FORMAT_INSTRUCTIONS = (
    "Your previous reply could not be parsed as JSON matching the schema. "
    "Reply again with ONLY valid JSON in the required format. If you cannot "
    "extract anything, return an empty list of objects."
)


def _make_structured_output_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """Force an LLM to answer in a declared schema (Langflow's Structured Output).

    The schema table becomes a Pydantic model, wrapped in ``objects:
    list[Model]`` exactly as Langflow does — its own format instructions say
    "Extract ALL relevant instances", so the result is always a list even when
    the text yields one object. A caller can rely on that shape.

    The extracted objects land in ``scratch[node.id]``; the same value also
    leaves as JSON text, which is what lets the result reach an agent or Chat
    Output (we have no DataFrame port type, so one output carries both).
    """
    from pydantic import Field as _PydanticField, create_model as _create_model

    from service.flow_model.output_schema import build_output_model

    rows = node.values.get("output_schema")
    schema_name = str(node.values.get("schema_name", "") or "OutputModel").strip()
    try:
        item_model = build_output_model(schema_name, rows)
    except ValueError as exc:
        raise FlowBuildError(f"StructuredOutput '{node.id}' has an unusable output schema: {exc}") from exc

    wrapper = _create_model(
        f"{schema_name}List",
        objects=(
            list[item_model],  # type: ignore[valid-type]
            _PydanticField(description=f"Every {schema_name} found in the text."),
        ),
    )

    instructions = str(node.values.get("system_prompt", "") or _DEFAULT_FORMAT_INSTRUCTIONS)
    input_source = str(node.values.get("input_source", "") or "")
    input_src = (port_sources or {}).get("input_text")

    schema_rows = [r for r in (rows or []) if isinstance(r, dict) and r.get("name")]
    scalar_fields = [str(r["name"]) for r in schema_rows if not r.get("multiple")]
    all_scalar = bool(schema_rows) and len(scalar_fields) == len(schema_rows)

    if model is None:
        from config_manager import env

        from infrastructure.llm import get_model

        model = get_model(env.DEFAULT_MODEL)

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if not hasattr(model, "with_structured_output"):
            raise FlowBuildError(
                f"StructuredOutput '{node.id}' is wired to a model that does not support structured output"
            )

        wired = _resolve_port_value(state, input_src)
        if wired is not None:
            text = str(wired)
        elif input_source:
            text = str(state.get("scratch", {}).get(input_source, ""))
        else:
            text = _extract_last_message_text(state)

        bound = model.with_structured_output(wrapper)
        # Recovery calls (parse retry, missing-field re-ask) must not stream
        # their tokens into the answer channel: a second JSON completion
        # concatenated onto the first is not valid JSON and breaks every
        # consumer of the visible output. ``skip_stream`` tells the SSE layer
        # to drop this call's chunks — the node still emits one clean final
        # message with the merged result.
        bound_quiet = bound.with_config({"tags": ["skip_stream"]})
        base_msgs = [SystemMessage(content=instructions), HumanMessage(content=text)]
        try:
            reply = await bound.ainvoke(base_msgs)
        except OutputParserException as first_exc:
            # The model returned something unparseable (often an empty string
            # from a small model). One stricter retry, then degrade to an
            # empty result — an unhandled parse error here 500s the whole
            # run (B1 crash mode).
            try:
                reply = await bound_quiet.ainvoke([*base_msgs, SystemMessage(content=_RETRY_FORMAT_INSTRUCTIONS)])
            except OutputParserException:
                logger.warning(
                    "StructuredOutput '%s' could not parse the model reply (%s); returning an empty result",
                    node.id,
                    first_exc,
                )
                report_stage_output(
                    node.id,
                    t("flow.structured_output_empty"),
                )
                return {
                    "scratch": {node.id: []},
                    "messages": [HumanMessage(content="[]")],
                }
        objects = [o.model_dump() if hasattr(o, "model_dump") else o for o in getattr(reply, "objects", []) or []]

        # B1 mitigations for small models:
        # 1) a small model often splits ONE record into several partial
        #    fragments (F05: the same fatura_no, everything else null, x3).
        #    Coalesce objects that don't actually conflict — same non-null
        #    scalar never disagrees — into one; genuinely distinct records
        #    (baslik "Bir" vs "Iki") conflict and are left alone.
        if all_scalar and len(objects) > 1:
            dicts = [o for o in objects if isinstance(o, dict)]

            def _compatible(a: dict, b: dict) -> bool:
                for f in scalar_fields:
                    av, bv = a.get(f), b.get(f)
                    if av not in (None, "") and bv not in (None, "") and av != bv:
                        return False
                return True

            coalesced: list[dict] = []
            for obj in dicts:
                for acc in coalesced:
                    if _compatible(acc, obj):
                        for f in scalar_fields:
                            if acc.get(f) in (None, "") and obj.get(f) not in (None, ""):
                                acc[f] = obj[f]
                        break
                else:
                    coalesced.append(dict(obj))
            if coalesced:
                objects = coalesced

        # 2) if scalar fields are still null but the source text is
        #    substantial, one targeted re-ask for exactly those fields.
        if all_scalar and objects and isinstance(objects[0], dict) and len(text) > 40:
            missing = [f for f in scalar_fields if objects[0].get(f) in (None, "")]
            if missing:
                try:
                    retry = await bound_quiet.ainvoke(
                        [
                            SystemMessage(content=instructions),
                            HumanMessage(content=text),
                            SystemMessage(
                                content=(
                                    "These fields are still missing: "
                                    + ", ".join(missing)
                                    + ". If the text contains their values, "
                                    "return one object with them filled; "
                                    "otherwise leave them null."
                                )
                            ),
                        ]
                    )
                    for o in getattr(retry, "objects", []) or []:
                        od = o.model_dump() if hasattr(o, "model_dump") else o
                        if not isinstance(od, dict):
                            continue
                        for f in missing:
                            if objects[0].get(f) in (None, "") and od.get(f) not in (
                                None,
                                "",
                            ):
                                objects[0][f] = od[f]
                except OutputParserException:
                    pass  # keep the partial result

        report_stage_output(
            node.id,
            t("flow.records_extracted", count=len(objects), schema=schema_name)
            if objects
            else t("flow.no_extractable_records", schema=schema_name),
        )
        return {
            "scratch": {node.id: objects},
            "messages": [HumanMessage(content=json.dumps(objects, ensure_ascii=False, default=str))],
        }

    return _run


def _render_processing_result(result: Any) -> str:
    """A readable message for any of the three result shapes."""
    import pandas as pd

    from service.flow_model.data_ops import format_result_as_text

    if isinstance(result, pd.DataFrame):
        return result.to_string(index=False)
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, default=str)
    return format_result_as_text(result)


def _make_operations_node(
    node: FlowNode,
    port_sources: dict[str, str] | None = None,
    extra_frame_sources: Sequence[str] | None = None,
) -> Any:
    """Langflow's Data Operations: thirty operations over Text, JSON and Table.

    Langflow picks the family with an ``input_type`` tab; its dispatch is by
    operation name alone and the three families share no name, so the operation
    is the only thing needed here too.

    ``extra_frame_sources`` carries the additional tables wired into ``df`` —
    Concatenate is the one operation that reads more than the first.
    """
    from service.flow_model.data_ops import (
        JSON_OPERATIONS,
        TABLE_OPERATIONS,
        TEXT_OPERATIONS,
        run_json_operation,
        run_table_operation,
        run_text_operation,
    )

    operation = str(node.values.get("operation", "") or "").strip()
    if not operation:
        raise FlowBuildError(f"Operations '{node.id}' has no operation selected")
    if operation not in (TEXT_OPERATIONS | JSON_OPERATIONS | TABLE_OPERATIONS):
        raise FlowBuildError(f"Operations '{node.id}' has an unknown operation: {operation!r}")

    values = dict(node.values)
    sources = dict(port_sources or {})
    frame_sources = [sources["df"]] if "df" in sources else []
    frame_sources.extend(extra_frame_sources or [])

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        if operation in TEXT_OPERATIONS:
            # Wired Text port, then the field, then what the flow just
            # produced. Langflow's text_input is a required wired input; ours
            # sits in a conversation, so the latest message is the sensible
            # last resort — the same chain every other node here uses.
            wired = _resolve_port_value(state, sources.get("text_input"))
            if wired is not None:
                text = str(wired)
            else:
                text = str(values.get("text_input", "") or "") or _extract_last_message_text(state)
            result = run_text_operation(operation, text, values)
            # Langflow's empty-text guard returns None; store the empty string
            # so a downstream reader gets a value of the right shape.
            if result is None:
                result = ""
        elif operation in JSON_OPERATIONS:
            data = _resolve_port_value(state, sources.get("data"))
            if data is None:
                data = {}
            result = run_json_operation(operation, data, values)
        else:
            frames = []
            for source in frame_sources:
                frame = _resolve_port_value(state, source)
                if frame is not None:
                    frames.append(frame)
            merge_values = dict(values)
            for side in ("left_dataframe", "right_dataframe"):
                if side in sources:
                    merge_values[side] = _resolve_port_value(state, sources[side])
            result = run_table_operation(operation, frames, merge_values)

        return {
            "scratch": {node.id: result},
            "messages": [HumanMessage(content=_render_processing_result(result))],
        }

    return _run


def _make_split_text_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """Langflow's Split Text: chunk text into one row per chunk."""
    from service.flow_model.data_ops import split_text

    values = dict(node.values)
    source = (port_sources or {}).get("data_inputs")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        wired = _resolve_port_value(state, source)
        payload = wired if wired is not None else _extract_last_message_text(state)
        try:
            frame = split_text(payload, values)
        except TypeError as exc:
            raise FlowBuildError(f"Split Text '{node.id}': {exc}") from exc
        return {
            "scratch": {node.id: frame},
            "messages": [HumanMessage(content=_render_processing_result(frame))],
        }

    return _run


def _make_type_converter_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """Langflow's Type Convert: Message <-> JSON <-> Table."""
    from service.flow_model.data_ops import convert_value

    output_type = str(node.values.get("output_type", "") or "Message")
    auto_parse = bool(node.values.get("auto_parse", False))
    source = (port_sources or {}).get("input_data")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        wired = _resolve_port_value(state, source)
        payload = wired if wired is not None else _extract_last_message_text(state)
        try:
            result = convert_value(payload, output_type, auto_parse=auto_parse)
        except ValueError as exc:
            raise FlowBuildError(f"TypeConverter '{node.id}': {exc}") from exc
        return {
            "scratch": {node.id: result},
            "messages": [HumanMessage(content=_render_processing_result(result))],
        }

    return _run


def make_component_tool(
    node: FlowNode,
    resources: ResolvedResources,
    *,
    node_factory: Any,
    user_id: str | None = None,
    mcp_tools_map: dict[str, Any] | None = None,
) -> Any:
    """Wrap one flow component as a LangChain tool.

    Each call copies the node with the model's arguments written over
    ``values``, rebuilds the node function from the same factory the flow
    would use, and runs it against a fresh ``FlowState``.

    Running the component's own function is what keeps a tool call and a flow
    step from ever drifting apart; the fresh state is what keeps a tool call
    from touching the flow's.
    """
    from langchain_core.tools import StructuredTool

    from service.flow_model.tool_schema import build_args_schema

    template = get_registry().get(node.type)
    args_schema = build_args_schema(template, node.values)

    async def _call(**kwargs: Any) -> tuple[Any, dict[str, str] | None]:
        call_node = node.model_copy(update={"values": {**node.values, **kwargs}})
        fn = await node_factory(
            call_node,
            resources,
            user_id=user_id,
            mcp_tools_map=mcp_tools_map,
        )
        # A retrieval component reports its evidence to this call, not to a
        # stage: the tool call is the step, so its ToolMessage carries the card.
        with capture_component_evidence() as evidence:
            result = await fn({"messages": [], "scratch": {}, "arrivals": []}, None)
        if len(evidence.ids) > 1:
            logger.warning(
                "Component tool %s reported %d evidences; keeping the last",
                node.id,
                len(evidence.ids),
            )
        artifact = {EVIDENCE_ARTIFACT_KEY: str(evidence.ids[-1])} if evidence.ids else None
        return result.get("scratch", {}).get(node.id), artifact

    return StructuredTool(
        name=derive_tool_name(node),
        description=template.description or template.display_name,
        args_schema=args_schema,
        coroutine=_call,
        response_format="content_and_artifact",
    )


def _make_parser_node(node: FlowNode, port_sources: dict[str, str] | None = None) -> Any:
    """Langflow's Parser: render structured data through a template.

    Two modes. ``Parser`` formats each row or item with the template;
    ``Stringify`` renders the whole value readably (a table as markdown, JSON
    as a fenced block) and ignores the template.
    """
    from service.flow_model.data_ops import parse_with_template, stringify_value

    mode = str(node.values.get("mode", "") or "Parser")
    pattern = str(node.values.get("pattern", "") or "")
    separator = str(node.values.get("sep", "\n") or "\n")
    clean_data = bool(node.values.get("clean_data", False))
    source = (port_sources or {}).get("input_data")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        wired = _resolve_port_value(state, source)
        payload = wired if wired is not None else _extract_last_message_text(state)
        try:
            if mode == "Stringify":
                text = stringify_value(payload, clean_data=clean_data)
            else:
                text = parse_with_template(payload, pattern, separator)
        except (KeyError, ValueError) as exc:
            raise FlowBuildError(f"Parser '{node.id}': {exc!r}") from exc
        return {
            "scratch": {node.id: text},
            "messages": [HumanMessage(content=text)],
        }

    return _run


MAX_BATCH_ROWS = 1000
MAX_BATCH_CONCURRENCY = 8


def _make_batch_run_node(
    node: FlowNode,
    model: BaseChatModel | None,
    port_sources: dict[str, str] | None = None,
) -> Any:
    """Langflow's Batch Run: one model call per row of a table.

    The whole table goes to the model in a single ``abatch``, and the answers
    come back as a new column beside the original rows. A blank column name
    sends the entire row, formatted the way Langflow does.
    """
    import pandas as pd

    column_name = str(node.values.get("column_name", "") or "")
    output_column = str(node.values.get("output_column_name", "") or "model_response")
    system_message = str(node.values.get("system_message", "") or "")
    source = (port_sources or {}).get("df")

    if model is None:
        from config_manager import env

        from infrastructure.llm import get_model

        model = get_model(env.DEFAULT_MODEL)

    def _row_as_text(row: dict[str, Any]) -> str:
        """Langflow renders a whole row as TOML-ish `col.value` lines."""
        return "\n".join(f'[{col}]\nvalue = "{val}"' for col, val in row.items())

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        frame = _resolve_port_value(state, source)
        if not isinstance(frame, pd.DataFrame):
            raise FlowBuildError(f"BatchRun '{node.id}' expects a table on its Table port, got {type(frame).__name__}")
        if column_name and column_name not in frame.columns:
            raise FlowBuildError(
                f"BatchRun '{node.id}': column '{column_name}' not found in the "
                f"table. Available columns: {', '.join(map(str, frame.columns))}"
            )

        if len(frame) > MAX_BATCH_ROWS:
            raise FlowBuildError(
                f"BatchRun '{node.id}': table has {len(frame)} rows, exceeding the {MAX_BATCH_ROWS}-row limit."
            )

        records = frame.to_dict(orient="records")
        texts = [str(row[column_name]) for row in records] if column_name else [_row_as_text(row) for row in records]

        conversations = [
            (
                [{"role": "system", "content": system_message}, {"role": "user", "content": text}]
                if system_message
                else [{"role": "user", "content": text}]
            )
            for text in texts
        ]

        replies = await model.abatch(conversations, config={"max_concurrency": MAX_BATCH_CONCURRENCY})
        rows: list[dict[str, Any]] = []
        for index, (row, reply) in enumerate(zip(records, replies, strict=False)):
            out = dict(row)
            out[output_column] = getattr(reply, "content", str(reply))
            out["batch_index"] = index
            rows.append(out)

        result = pd.DataFrame(rows)
        return {
            "scratch": {node.id: result},
            "messages": [HumanMessage(content=_render_processing_result(result))],
        }

    return _run
