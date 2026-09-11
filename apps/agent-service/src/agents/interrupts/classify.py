"""Bekleyen bir interrupt payload'ının hangi tür olduğunu söyler.

Tek bir thread'de birden fazla interrupt türü olabiliyor: flow canvas'ının
HumanInput node'u, araç onay kapısı ve `ask_user`. Her biri farklı paket,
farklı renderer ve farklı resume şekli istiyor, dolayısıyla ayırt etmek
zorunlu.

Türlerin çoğu kendi ``type`` alanını taşıyor. Tek istisna HITLRequest:
onda ``type`` alanı YOK (langchain 1.0.7, human_in_the_loop.py:
HITLRequest) — şeklinden tanımak tek yol.
"""

from typing import Any

HUMAN_INPUT = "human_input"
TOOL_APPROVAL = "tool_approval"
USER_CLARIFICATION = "user_clarification"

_BY_TYPE = frozenset({HUMAN_INPUT, USER_CLARIFICATION})


def classify_interrupt(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    declared = value.get("type")
    if declared in _BY_TYPE:
        return str(declared)
    if "action_requests" in value and "review_configs" in value:
        return TOOL_APPROVAL
    return None
