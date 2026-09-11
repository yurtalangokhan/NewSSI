"""Bekleyen bir interrupt payload'ını tanınmış bir :class:`PendingInterrupt`'e çevirir.

Interrupt'ı bulan tarama :meth:`ThreadController.get_pending_interrupt`'te:
checkpointer'ın ``alist``'i thread'in HER namespace'ini geziyor (kök +
supervisor alt agent'ları + pipeline aşamaları + flow'un ReActAgent node'u),
dolayısıyla derlenmiş bir graf ya da özyinelemeli bir state gezintisi
gerekmiyor. Burası yalnızca tek bir ``__interrupt__`` yazımını yorumluyor.
"""

from dataclasses import dataclass
from typing import Any

from agents.interrupts.classify import TOOL_APPROVAL, classify_interrupt


@dataclass(frozen=True)
class PendingInterrupt:
    kind: str
    value: Any
    interrupt_id: str
    action_count: int


def _as_pending(interrupt: Any) -> PendingInterrupt | None:
    """Bir ``Interrupt`` (ya da çıplak değer) → :class:`PendingInterrupt` / ``None``.

    ``None``: değer bilinen türlerden birine uymuyor (ör. bir agent'ın düz
    string prompt'u). Çağıran bunu "bu yazım bizim değil, sonrakine bak"
    olarak okur.
    """
    value = getattr(interrupt, "value", interrupt)
    kind = classify_interrupt(value)
    if kind is None:
        return None
    action_count = len(value.get("action_requests") or []) if kind == TOOL_APPROVAL else 0
    return PendingInterrupt(
        kind=kind,
        value=value,
        interrupt_id=str(getattr(interrupt, "id", "") or ""),
        action_count=action_count,
    )
