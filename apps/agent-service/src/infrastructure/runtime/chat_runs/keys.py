"""Redis key schema for chat runs (see design.md, "Redis key schema")."""

RUN_PREFIX = "chat_run:"
RUNNING_SET_KEY = "chat_runs:running"


def run_key(run_id: str) -> str:
    return f"{RUN_PREFIX}{run_id}"


def events_key(run_id: str) -> str:
    return f"{RUN_PREFIX}{run_id}:events"


def lease_key(run_id: str) -> str:
    return f"{RUN_PREFIX}{run_id}:lease"


def cancel_key(run_id: str) -> str:
    return f"{RUN_PREFIX}{run_id}:cancel"


def thread_lock_key(thread_id: str) -> str:
    return f"chat_thread:{thread_id}:active_run"


def request_cancel_key(thread_id: str, client_request_id: str) -> str:
    # Scoped to the thread: only its owner can stop it (see stop_chat_session).
    return f"chat_thread:{thread_id}:request_cancel:{client_request_id}"


def naming_lock_key(thread_id: str) -> str:
    return f"chat_thread:{thread_id}:naming"
