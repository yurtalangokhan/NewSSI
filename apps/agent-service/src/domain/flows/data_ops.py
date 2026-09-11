"""Data Operations — a faithful port of Langflow's ``OperationsComponent``.

Thirty operations in three families (JSON, Table, Text). Every body here is
taken from Langflow's own implementation rather than inferred from the
operation's name: the product rule for this port is that an operation sharing
Langflow's name must produce Langflow's result.

Where Langflow does something surprising, the surprise is the contract:

- ``Select Keys`` treats a lone ``"data"`` selection as "unwrap that key".
- ``Path Selection`` swallows its error and returns ``{"error": ...}``, while
  ``JQ Expression`` raises. Both behaviours are theirs.
- ``Word Count`` is a Text operation that outputs JSON, and
  ``Text to DataFrame`` is a Text operation that outputs a table.

Pure: no I/O, no state. The node factory in ``flow_builder`` supplies the
inputs and stores the result.

Langflow's vocabulary, which the rest of this file follows: its ``Data`` is
displayed as **JSON**, its ``DataFrame`` as **Table**.
"""

from __future__ import annotations

import ast
import contextlib
import json
import re
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# The inventory, in Langflow's display order
# ---------------------------------------------------------------------------

TEXT_OPERATION_ORDER: tuple[str, ...] = (
    "Word Count",
    "Case Conversion",
    "Text Replace",
    "Text Extract",
    "Text Head",
    "Text Tail",
    "Text Strip",
    "Text Join",
    "Text Clean",
    "Text to DataFrame",
)

JSON_OPERATION_ORDER: tuple[str, ...] = (
    "Select Keys",
    "Literal Eval",
    "Combine",
    "Append or Update",
    "Remove Keys",
    "Rename Keys",
    "Path Selection",
    "JQ Expression",
)

TABLE_OPERATION_ORDER: tuple[str, ...] = (
    "Add Column",
    "Concatenate",
    "Drop Column",
    "Filter",
    "Head",
    "Merge",
    "Rename Column",
    "Replace Value",
    "Select Columns",
    "Sort",
    "Tail",
    "Drop Duplicates",
)

TEXT_OPERATIONS = frozenset(TEXT_OPERATION_ORDER)
JSON_OPERATIONS = frozenset(JSON_OPERATION_ORDER)
TABLE_OPERATIONS = frozenset(TABLE_OPERATION_ORDER)

#: Every operation, grouped the way Langflow's picker groups them. A single
#: field carries all thirty here — Langflow splits the picker by an
#: ``input_type`` tab, but its dispatch is by operation name alone, and the
#: three families share no name.
ALL_OPERATIONS: tuple[str, ...] = (
    *TEXT_OPERATION_ORDER,
    *JSON_OPERATION_ORDER,
    *TABLE_OPERATION_ORDER,
)

#: Operations whose output is a table, including the one Text operation that
#: produces one.
DATAFRAME_OUTPUT_OPERATIONS = frozenset({*TABLE_OPERATION_ORDER, "Text to DataFrame"})
#: Operations whose output is JSON, including the one Text operation that is.
DATA_OUTPUT_OPERATIONS = frozenset({*JSON_OPERATION_ORDER, "Word Count"})
#: The rest — plain text out.
MESSAGE_OUTPUT_OPERATIONS = frozenset(TEXT_OPERATION_ORDER) - {
    "Word Count",
    "Text to DataFrame",
}

CASE_CONVERTERS: dict[str, Any] = {
    "uppercase": str.upper,
    "lowercase": str.lower,
    "title": str.title,
    "capitalize": str.capitalize,
    "swapcase": str.swapcase,
}

FILTER_OPERATORS: tuple[str, ...] = (
    "equals",
    "not equals",
    "contains",
    "not contains",
    "starts with",
    "ends with",
    "greater than",
    "less than",
)

MERGE_TYPES: tuple[str, ...] = ("inner", "outer", "left", "right")
STRIP_MODES: tuple[str, ...] = ("both", "left", "right")


# ---------------------------------------------------------------------------
# JSON family
# ---------------------------------------------------------------------------


def _as_list(data: Any) -> list[Any]:
    return data if isinstance(data, list) else [data]


def _is_multiple(data: Any) -> bool:
    """Langflow's ``data_is_list``: more than one object, not merely a list."""
    return isinstance(data, list) and len(data) > 1


def _data_dict(data: Any) -> dict[str, Any]:
    """Langflow's ``get_data_dict``: a lone item in a list is that item.

    Its ``Data.model_dump()`` becomes the plain dict we already carry, so the
    mapping is the identity once the single-item list is unwrapped.
    """
    if isinstance(data, list):
        if len(data) == 1:
            data = data[0]
        elif not data:
            return {}
    return dict(data) if isinstance(data, dict) else {"data": data}


def _normalized(data: Any) -> dict[str, Any]:
    """Langflow's ``get_normalized_data``: unwrap a ``data`` envelope if any."""
    data_dict = _data_dict(data)
    inner = data_dict.get("data", data_dict)
    return dict(inner) if isinstance(inner, dict) else data_dict


def _require_single(data: Any, operation: str) -> None:
    if _is_multiple(data):
        msg = f"{operation} operation is not supported for multiple data objects."
        raise ValueError(msg)


def _remove_keys_recursive(obj: Any, keys_to_remove: set[str]) -> Any:
    if isinstance(obj, dict):
        return {
            k: _remove_keys_recursive(v, keys_to_remove)
            for k, v in obj.items()
            if k not in keys_to_remove
        }
    if isinstance(obj, list):
        return [_remove_keys_recursive(item, keys_to_remove) for item in obj]
    return obj


def _rename_keys_recursive(obj: Any, rename_map: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {rename_map.get(k, k): _rename_keys_recursive(v, rename_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rename_keys_recursive(item, rename_map) for item in obj]
    return obj


def _recursive_eval(data: Any) -> Any:
    """Langflow's ``recursive_eval``.

    Only a string that *looks* like a literal is even attempted: it starts
    with one of ``{ [ ( ' "``, reads as true/false/none, or is all digits once
    dots are removed. Anything that fails to parse is kept as it was, so prose
    is never mangled.
    """
    if isinstance(data, dict):
        return {k: _recursive_eval(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_recursive_eval(item) for item in data]
    if isinstance(data, str):
        stripped = data.strip()
        looks_literal = (
            stripped.startswith(("{", "[", "(", "'", '"'))
            or stripped.lower() in ("true", "false", "none")
            or stripped.replace(".", "").isdigit()
        )
        if looks_literal:
            try:
                return ast.literal_eval(data)
            except (ValueError, SyntaxError, TypeError, MemoryError):
                return data
        return data
    return data


def _select_keys(data: Any, values: dict[str, Any]) -> dict[str, Any]:
    _require_single(data, "Select Keys")
    data_dict = _normalized(data)
    criteria = list(values.get("select_keys_input") or [])

    if len(criteria) == 1 and criteria[0] == "data":
        return data_dict["data"]

    missing = [key for key in criteria if key not in data_dict]
    if missing:
        msg = f"Select key not found in data. Available keys: {list(data_dict.keys())}"
        raise ValueError(msg)
    return {key: value for key, value in data_dict.items() if key in criteria}


def _combine(data: Any) -> dict[str, Any]:
    if not _is_multiple(data):
        items = _as_list(data)
        return _data_dict(items[0]) if items else {}

    combined: dict[str, Any] = {}
    for item in data:
        item_dict = _data_dict(item)
        item_dict = item_dict.get("data", item_dict)
        if not isinstance(item_dict, dict):
            continue
        for key, value in item_dict.items():
            if key not in combined:
                combined[key] = value
            elif isinstance(combined[key], list):
                if isinstance(value, list):
                    combined[key].extend(value)
                else:
                    combined[key].append(value)
            else:
                combined[key] = (
                    [combined[key], value]
                    if not isinstance(value, list)
                    else [combined[key], *value]
                )
    return combined


def _jq_input(data: Any) -> Any:
    payload = _as_list(data)[0] if isinstance(data, list) else data
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _path_selection(data: Any, values: dict[str, Any]) -> dict[str, Any]:
    import jq

    selected_key = values.get("selected_key") or ""
    try:
        if not data or not selected_key:
            msg = "Missing input data or selected key."
            raise ValueError(msg)
        result = jq.compile(selected_key).input(_jq_input(data)).first()
    except (ValueError, TypeError, KeyError) as e:
        # Langflow reports this one instead of raising; JQ Expression raises.
        return {"error": str(e)}
    if isinstance(result, dict):
        return result
    return {"result": result}


def _jq_expression(data: Any, values: dict[str, Any]) -> dict[str, Any]:
    import jq
    from json_repair import repair_json

    query = str(values.get("query") or "")
    if not query.strip():
        msg = "JSON Query is required and cannot be blank."
        raise ValueError(msg)

    raw_data = _data_dict(data)
    try:
        data_json = json.loads(repair_json(json.dumps(raw_data)))
        jq_in = (
            data_json["data"] if isinstance(data_json, dict) and "data" in data_json else data_json
        )
        results = jq.compile(query).input(jq_in).all()
        if not results:
            msg = "No result from JSON query."
            raise ValueError(msg)
        result = results[0] if len(results) == 1 else results
        if result is None or result == "None":
            msg = "JSON query returned null/None. Check if the path exists in your data."
            raise ValueError(msg)
    except (TypeError, KeyError, json.JSONDecodeError) as e:
        msg = f"JSON Query error: {e}"
        raise ValueError(msg) from e
    if isinstance(result, dict):
        return result
    return {"result": result}


def run_json_operation(operation: str, data: Any, values: dict[str, Any]) -> dict[str, Any]:
    """One JSON-family operation. Returns the resulting object."""
    if operation == "Select Keys":
        return _select_keys(data, values)
    if operation == "Literal Eval":
        _require_single(data, "Literal Eval")
        return _recursive_eval(_data_dict(data))
    if operation == "Combine":
        return _combine(data)
    if operation == "Append or Update":
        _require_single(data, "Append or Update")
        result = _normalized(data)
        for key, value in (values.get("append_update_data") or {}).items():
            result[key] = value
        return result
    if operation == "Remove Keys":
        _require_single(data, "Remove Keys")
        return _remove_keys_recursive(_normalized(data), set(values.get("remove_keys_input") or []))
    if operation == "Rename Keys":
        _require_single(data, "Rename Keys")
        return _rename_keys_recursive(
            _normalized(data), dict(values.get("rename_keys_input") or {})
        )
    if operation == "Path Selection":
        return _path_selection(data, values)
    if operation == "JQ Expression":
        return _jq_expression(data, values)
    msg = f"Unsupported operation: {operation}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Table family
#
# Langflow calls its DataFrame type "Table". Every body below is its pandas
# call, kept literal — the filter's numeric fallback, Merge's suffix folding
# and Drop Duplicates' subset are all behaviours a paraphrase would lose.
# ---------------------------------------------------------------------------


def _primary_frame(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """The frame an operation works on — always a copy, so a node never edits
    the value another consumer is still reading out of scratch."""
    if not frames:
        return pd.DataFrame()
    return frames[0].copy()


def _filter_rows(df: pd.DataFrame, values: dict[str, Any]) -> pd.DataFrame:
    column = df[values.get("column_name")]
    filter_value = values.get("filter_value")
    operator = values.get("filter_operator") or "equals"

    if operator == "equals":
        mask = column == filter_value
    elif operator == "not equals":
        mask = column != filter_value
    elif operator == "contains":
        mask = column.astype(str).str.contains(str(filter_value), na=False)
    elif operator == "not contains":
        mask = ~column.astype(str).str.contains(str(filter_value), na=False)
    elif operator == "starts with":
        mask = column.astype(str).str.startswith(str(filter_value), na=False)
    elif operator == "ends with":
        mask = column.astype(str).str.endswith(str(filter_value), na=False)
    elif operator in ("greater than", "less than"):
        try:
            numeric_value = pd.to_numeric(filter_value)
            mask = column > numeric_value if operator == "greater than" else column < numeric_value
        except (ValueError, TypeError):
            text = column.astype(str)
            mask = (
                text > str(filter_value) if operator == "greater than" else text < str(filter_value)
            )
    else:
        # Langflow's fallback for an operator it does not know.
        mask = column == filter_value

    return df[mask]


def _concatenate(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    if len(frames) == 1:
        return frames[0].copy()
    return pd.concat(frames, ignore_index=True)


def _merge(values: dict[str, Any]) -> pd.DataFrame:
    left = values.get("left_dataframe")
    right = values.get("right_dataframe")
    if left is None:
        return pd.DataFrame()
    if right is None:
        return left.copy()

    df_left, df_right = left.copy(), right.copy()
    merge_on = values.get("merge_on_column")
    merge_how = values.get("merge_how") or "inner"

    if merge_on:
        if merge_on not in df_left.columns:
            msg = f"Column '{merge_on}' not found in left DataFrame. Available: {list(df_left.columns)}"
            raise ValueError(msg)
        if merge_on not in df_right.columns:
            msg = f"Column '{merge_on}' not found in right DataFrame. Available: {list(df_right.columns)}"
            raise ValueError(msg)
        merged = df_left.merge(df_right, on=merge_on, how=merge_how, suffixes=("", "_right"))
    else:
        merged = df_left.merge(
            df_right, left_index=True, right_index=True, how=merge_how, suffixes=("", "_right")
        )

    # Fold each `_right` column back into its original and drop it, so an
    # overlapping column comes out filled rather than duplicated.
    to_drop = []
    for col in merged.columns:
        if col.endswith("_right"):
            original = col[:-6]
            if original in merged.columns:
                merged[original] = merged[original].combine_first(merged[col])
                to_drop.append(col)
    if to_drop:
        merged = merged.drop(columns=to_drop)
    return merged


def run_table_operation(
    operation: str, frames: list[pd.DataFrame], values: dict[str, Any]
) -> pd.DataFrame:
    """One Table-family operation. ``frames`` is every table wired in."""
    if operation == "Merge":
        return _merge(values)
    if operation == "Concatenate":
        return _concatenate(frames)

    df = _primary_frame(frames)
    if operation == "Filter":
        return _filter_rows(df, values)
    if operation == "Sort":
        return df.sort_values(
            by=values.get("column_name"), ascending=bool(values.get("ascending", True))
        )
    if operation == "Drop Column":
        return df.drop(columns=[values.get("column_name")])
    if operation == "Rename Column":
        return df.rename(columns={values.get("column_name"): values.get("new_column_name")})
    if operation == "Add Column":
        df[values.get("new_column_name")] = [values.get("new_column_value")] * len(df)
        return df
    if operation == "Select Columns":
        columns = [str(col).strip() for col in (values.get("columns_to_select") or [])]
        return df[columns]
    if operation == "Head":
        return df.head(int(values.get("num_rows", 5)))
    if operation == "Tail":
        return df.tail(int(values.get("num_rows", 5)))
    if operation == "Replace Value":
        column = values.get("column_name")
        df[column] = df[column].replace(
            values.get("replace_value"), values.get("replacement_value")
        )
        return df
    if operation == "Drop Duplicates":
        return df.drop_duplicates(subset=values.get("column_name"))
    msg = f"Unsupported operation: {operation}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Text family
#
# Two of these leave the family's output type, which is Langflow's routing:
# `Word Count` produces JSON and `Text to DataFrame` produces a table.
# ---------------------------------------------------------------------------


def _word_count(text: str, values: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    text_str = str(text) if text else ""
    is_empty = not text_str or not text_str.strip()

    if values.get("count_words", True):
        if is_empty:
            result["word_count"] = 0
            result["unique_words"] = 0
        else:
            words = text_str.split()
            result["word_count"] = len(words)
            result["unique_words"] = len(set(words))

    if values.get("count_characters", True):
        if is_empty:
            result["character_count"] = 0
            result["character_count_no_spaces"] = 0
        else:
            result["character_count"] = len(text_str)
            result["character_count_no_spaces"] = len(text_str.replace(" ", ""))

    if values.get("count_lines", True):
        if is_empty:
            result["line_count"] = 0
            result["non_empty_lines"] = 0
        else:
            lines = text_str.split("\n")
            result["line_count"] = len(lines)
            result["non_empty_lines"] = len([line for line in lines if line.strip()])

    return result


def _text_replace(text: str, values: dict[str, Any]) -> str:
    search_pattern = values.get("search_pattern") or ""
    if not search_pattern:
        return text
    replacement = values.get("replacement_text") or ""
    if values.get("use_regex", False):
        try:
            return re.sub(search_pattern, replacement, text)
        except re.error:
            # Langflow logs and returns the input rather than failing the run.
            return text
    return text.replace(search_pattern, replacement)


def _text_extract(text: str, values: dict[str, Any]) -> list[str]:
    pattern = values.get("extract_pattern") or ""
    if not pattern:
        return []
    max_matches = int(values.get("max_matches", 10))
    try:
        matches = re.findall(pattern, text)
    except re.error as e:
        msg = f"Invalid regex pattern '{pattern}': {e}"
        raise ValueError(msg) from e
    return matches[:max_matches] if max_matches > 0 else matches


def _text_head(text: str, values: dict[str, Any]) -> str:
    count = int(values.get("head_characters", 100))
    if count < 0:
        msg = f"Characters from Start must be a non-negative integer, got {count}"
        raise ValueError(msg)
    return "" if count == 0 else text[:count]


def _text_tail(text: str, values: dict[str, Any]) -> str:
    count = int(values.get("tail_characters", 100))
    if count < 0:
        msg = f"Characters from End must be a non-negative integer, got {count}"
        raise ValueError(msg)
    return "" if count == 0 else text[-count:]


def _text_strip(text: str, values: dict[str, Any]) -> str:
    mode = values.get("strip_mode", "both")
    characters = values.get("strip_characters") or None
    text_str = str(text) if text else ""
    if mode == "left":
        return text_str.lstrip(characters)
    if mode == "right":
        return text_str.rstrip(characters)
    return text_str.strip(characters)


def _text_join(text: str, values: dict[str, Any]) -> str:
    text1 = str(text) if text else ""
    text2 = str(values.get("text_input_2") or "")
    if text1 and text2:
        return f"{text1}\n{text2}"
    return text1 or text2


def _text_clean(text: str, values: dict[str, Any]) -> str:
    result = text
    if values.get("remove_extra_spaces", True):
        # Horizontal whitespace only — newlines survive, so remove_empty_lines
        # still has lines to work with when both options are on.
        result = re.sub(r"[^\S\n]+", " ", result)
    if values.get("remove_special_chars", False):
        result = re.sub(r"[^\w\s]", "", result)
    if values.get("remove_empty_lines", False):
        result = "\n".join(line for line in result.split("\n") if line.strip())
    return result


def _text_to_dataframe(text: str, values: dict[str, Any]) -> pd.DataFrame:
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return pd.DataFrame()

    separator = values.get("table_separator") or "|"
    has_header = bool(values.get("has_header", True))

    rows = []
    for line in lines:
        cleaned = line.strip(separator)
        rows.append([cell.strip() for cell in cleaned.split(separator)])
    if not rows:
        return pd.DataFrame()

    if has_header and len(rows) > 1:
        header, data_rows = rows[0], rows[1:]
        for index, row in enumerate(data_rows):
            if len(row) != len(header):
                msg = (
                    f"Header mismatch: {len(header)} column(s) in header vs "
                    f"{len(row)} column(s) in data row {index + 1}. "
                    "Please ensure the header has the same number of columns as your data."
                )
                raise ValueError(msg)
        df = pd.DataFrame(data_rows, columns=header)
    else:
        max_cols = max(len(row) for row in rows)
        df = pd.DataFrame(rows, columns=[f"col_{i}" for i in range(max_cols)])

    for col in df.columns:
        with contextlib.suppress(ValueError, TypeError):
            df[col] = pd.to_numeric(df[col])
    return df


def format_result_as_text(result: Any) -> str:
    """Langflow's ``_format_result_as_text``: a list becomes one item per line."""
    if result is None:
        return ""
    if isinstance(result, list):
        return "\n".join(str(item) for item in result)
    return str(result)


def run_text_operation(operation: str, text: str, values: dict[str, Any]) -> Any:
    """One Text-family operation.

    Returns ``None`` for empty input, which is Langflow's own guard — except
    for ``Text Join``, whose second input may carry the content.
    """
    if operation == "Word Count":
        return _word_count(text, values)
    if operation == "Text to DataFrame":
        return _text_to_dataframe(text or "", values)

    if not text and operation != "Text Join":
        return None

    if operation == "Case Conversion":
        converter = CASE_CONVERTERS.get(values.get("case_type", "lowercase"))
        return converter(text) if converter else text
    if operation == "Text Replace":
        return _text_replace(text, values)
    if operation == "Text Extract":
        return _text_extract(text, values)
    if operation == "Text Head":
        return _text_head(text, values)
    if operation == "Text Tail":
        return _text_tail(text, values)
    if operation == "Text Strip":
        return _text_strip(text, values)
    if operation == "Text Join":
        return _text_join(text, values)
    if operation == "Text Clean":
        return _text_clean(text, values)
    msg = f"Unsupported operation: {operation}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Type Convert  (Langflow's TypeConverterComponent)
#
# Message <-> JSON (its Data) <-> Table (its DataFrame). This is also the
# sanctioned way out of the deliberate `DATA -> DATAFRAME` incompatibility in
# handle_types: a JSON object is not a table, but this converts one.
# ---------------------------------------------------------------------------

#: Langflow's CSV heuristic needs at least this many lines before it will even
#: look at the header for a comma.
_MIN_CSV_LINES = 2

CONVERT_OUTPUT_TYPES: tuple[str, ...] = ("Message", "JSON", "Table")


def _try_parse_json(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
        return {"records": parsed}
    return None


def _looks_like_csv(text: str) -> bool:
    lines = text.strip().split("\n")
    if len(lines) < _MIN_CSV_LINES:
        return False
    return "," in lines[0] and len(lines) > 1


def _parse_structured_text(text: str) -> dict[str, Any]:
    """Langflow's ``parse_structured_data``: JSON first, then CSV, else keep."""
    from io import StringIO

    cleaned = text.lstrip("﻿").strip()

    parsed = _try_parse_json(cleaned)
    if parsed is not None:
        return parsed

    if _looks_like_csv(cleaned):
        try:
            frame = pd.read_csv(StringIO(cleaned))
        except Exception:  # noqa: BLE001 - a heuristic misfire keeps the text
            return {"text": text}
        return {"records": frame.to_dict(orient="records")}

    return {"text": text}


def _to_json(value: Any, *, auto_parse: bool) -> dict[str, Any]:
    if isinstance(value, pd.DataFrame):
        return {"records": value.to_dict(orient="records")}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"records": value}
    text = "" if value is None else str(value)
    return _parse_structured_text(text) if auto_parse else {"text": text}


def _json_to_table(payload: dict[str, Any]) -> pd.DataFrame:
    """Langflow's ``Data.to_dataframe``.

    A payload with exactly one key whose value is a list of objects opens into
    the table itself; anything else becomes a single row.
    """
    if len(payload) == 1:
        only = next(iter(payload.values()))
        if isinstance(only, list) and all(isinstance(item, dict) for item in only):
            return pd.DataFrame(only)
    return pd.DataFrame([payload])


def convert_value(value: Any, output_type: str, *, auto_parse: bool = False) -> Any:
    """Convert between Message, JSON and Table."""
    if output_type == "Message":
        if isinstance(value, pd.DataFrame):
            return value.to_string()
        return "" if value is None else str(value)
    if output_type == "JSON":
        return _to_json(value, auto_parse=auto_parse)
    if output_type == "Table":
        if isinstance(value, pd.DataFrame):
            return value
        if isinstance(value, list):
            return pd.DataFrame(value)
        return _json_to_table(_to_json(value, auto_parse=auto_parse))
    msg = f"Unsupported output type: {output_type}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Split Text  (Langflow's SplitTextComponent)
# ---------------------------------------------------------------------------

KEEP_SEPARATOR_CHOICES: tuple[str, ...] = ("False", "True", "Start", "End")


def _fix_separator(separator: str) -> str:
    """Langflow fixes the two typos people actually make, then unescapes."""
    if separator == "/n":
        separator = "\n"
    elif separator == "/t":
        separator = "\t"
    return separator.replace("\\n", "\n")


def _keep_separator(value: Any) -> Any:
    """ "False"/"True" become booleans; "Start"/"End" stay strings."""
    if isinstance(value, str):
        if value.lower() == "false":
            return False
        if value.lower() == "true":
            return True
    return value


def split_text(source: Any, values: dict[str, Any]) -> pd.DataFrame:
    """Split text into chunks, returning one row per chunk.

    Uses LangChain's ``CharacterTextSplitter`` with Langflow's parameters, so
    the chunk boundaries are the same ones Langflow would produce.
    """
    from langchain_text_splitters import CharacterTextSplitter

    text_key = str(values.get("text_key") or "text")

    if isinstance(source, pd.DataFrame):
        if source.empty:
            msg = "DataFrame is empty"
            raise TypeError(msg)
        texts = [str(v) for v in source[text_key].tolist()]
    elif isinstance(source, dict):
        texts = [str(source.get(text_key, ""))]
    elif isinstance(source, list):
        texts = [
            str(item.get(text_key, "")) if isinstance(item, dict) else str(item) for item in source
        ]
    else:
        texts = [str(source or "")]

    if not any(texts):
        msg = "No data inputs provided"
        raise TypeError(msg)

    splitter = CharacterTextSplitter(
        chunk_overlap=int(values.get("chunk_overlap", 200)),
        chunk_size=int(values.get("chunk_size", 1000)),
        separator=_fix_separator(str(values.get("separator", "\n"))),
        keep_separator=_keep_separator(values.get("keep_separator", "False")),
    )
    try:
        chunks: list[str] = []
        for text in texts:
            chunks.extend(splitter.split_text(text))
    except Exception as e:
        msg = f"Error splitting text: {e}"
        raise TypeError(msg) from e

    return pd.DataFrame({text_key: chunks})


# ---------------------------------------------------------------------------
# Parser  (Langflow's ParserComponent)
#
# Two modes, and the asymmetry between them is Langflow's own: over a table the
# template uses `format(**row)`, which raises on a missing column; over JSON it
# uses `format_map` with a defaulting dict, which substitutes an empty string.
# ---------------------------------------------------------------------------

PARSER_MODES: tuple[str, ...] = ("Parser", "Stringify")


class _DefaultingDict(dict):
    """A mapping whose missing keys render as an empty string.

    Langflow's ``_DefaultDict``: a template over JSON keeps rendering when a
    key is absent instead of failing the whole flow.
    """

    def __missing__(self, key: str) -> str:
        return ""


def _clean_string(text: str) -> str:
    """Langflow's ``clean_string``: empty out blank lines, collapse long runs."""
    text = re.sub(r"^\s*$", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text)


def parse_with_template(value: Any, pattern: str, separator: str = "\n") -> str:
    """Render ``value`` through ``pattern``, one line per row or item."""
    if isinstance(value, pd.DataFrame):
        lines = [pattern.format(**row) for row in value.to_dict(orient="records")]
    elif isinstance(value, dict):
        lines = [pattern.format_map(_DefaultingDict(value))]
    elif isinstance(value, list):
        lines = [
            pattern.format_map(_DefaultingDict(item if isinstance(item, dict) else {}))
            for item in value
        ]
    else:
        msg = (
            f"Unsupported input type: {type(value)}. Expected a table, a JSON "
            "object, or a list of them."
        )
        raise ValueError(msg)
    return separator.join(lines)


def stringify_value(value: Any, *, clean_data: bool = False) -> str:
    """Langflow's ``safe_convert``: a readable string for any of the shapes.

    A table becomes a markdown table; a JSON object a fenced ``json`` block;
    text is cleaned. ``clean_data`` additionally drops a table's empty rows and
    collapses whitespace inside its cells.
    """
    if isinstance(value, str):
        return _clean_string(value)
    if isinstance(value, pd.DataFrame):
        frame = value
        if clean_data:
            frame = frame.dropna(how="all")
            frame = frame.replace(r"^\s*$", "", regex=True)
            frame = frame.replace(r"\n+", "\n", regex=True)
        # Escape pipes so a cell cannot break the markdown table.
        frame = frame.replace(r"\|", r"\\|", regex=True)
        return frame.to_markdown(index=False)
    if isinstance(value, dict):
        return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n```"
    if isinstance(value, list):
        return "\n".join(stringify_value(item, clean_data=clean_data) for item in value)
    return _clean_string(str(value))
