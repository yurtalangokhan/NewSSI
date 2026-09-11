"""`_collect_update_messages`'in interrupt dikişi: duraklayan bir çalışma
istemciye ölü bir akış değil, tipli bir paket olarak ulaşmalı.

Tasarım §10 "Entegrasyon" listesindeki "Çalışma duruyor; araç sonucu henüz
yok; paket doğru" maddesi burada sabitleniyor. `ask_user` aracının kendi
testi (`tests/agents/clarification/test_tool.py`) interrupt DEĞERİNİ
doğruluyor; bu test o değerin SSE paketine dönüşünü doğruluyor.
"""

import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.types import Interrupt

from service.AgentStreamService import _collect_update_messages


async def _collect(value, interrupt_id="int-1"):
    """`_collect_update_messages`'i tek bir interrupt ile koşturur.

    ``ctx`` ve ``is_dynamic_agent`` yalnızca interrupt dışı dallarda
    kullanılıyor, dolayısıyla burada önemsiz.
    """
    new_messages: list = []
    event = {"__interrupt__": [Interrupt(value=value, id=interrupt_id)]}
    yielded = [
        chunk
        async for chunk in _collect_update_messages(
            ctx=None,
            event=event,
            stream_mode="updates",
            is_dynamic_agent=False,
            new_messages=new_messages,
        )
    ]
    return yielded, new_messages


def _parse(raw):
    assert raw.startswith("data: ") and raw.endswith("\n\n")
    return json.loads(raw[len("data: ") :].strip())


def _one_packet(yielded):
    """The clarification packet — the frames after it (a `stop`) are ignored."""
    assert yielded, yielded
    return _parse(yielded[0])


CLARIFICATION_VALUE = {
    "type": "user_clarification",
    "v": 1,
    "questions": [
        {
            "question": "Raporu kim okuyacak?",
            "header": "Hedef kitle",
            "options": [{"label": "Yönetim"}, {"label": "Teknik ekip"}],
            "multiSelect": False,
        }
    ],
    "agent_path": ["Destek Supervisor", "Fatura Uzmanı"],
}


@pytest.mark.asyncio
async def test_a_clarification_interrupt_ships_as_its_own_packet():
    yielded, new_messages = await _collect(CLARIFICATION_VALUE, interrupt_id="int-42")

    packet = _one_packet(yielded)
    assert packet["type"] == "user_clarification"
    assert packet["v"] == 1
    # request_id, interrupt'ın kendi id'sinden gelir — resume ve kilitleme
    # paketi aynı karta bunun üzerinden bağlanır.
    assert packet["request_id"] == "int-42"
    assert packet["questions"] == CLARIFICATION_VALUE["questions"]
    assert packet["agent_path"] == ["Destek Supervisor", "Fatura Uzmanı"]
    # Duraklama bir mesaj DEĞİL: modele giden bir AIMessage üretilmemeli.
    assert new_messages == []
    # ...and a `stop` right after, so the live client's pacing reveals the
    # card instead of leaving it queued until a reload.
    assert [_parse(f)["type"] for f in yielded] == ["user_clarification", "stop"]


@pytest.mark.asyncio
async def test_a_single_agent_clarification_has_an_empty_agent_path():
    value = {**CLARIFICATION_VALUE}
    value.pop("agent_path")

    packet = _one_packet((await _collect(value))[0])

    assert packet["agent_path"] == []


@pytest.mark.asyncio
async def test_a_human_input_interrupt_is_still_shipped_unchanged():
    """Regresyon: aynı dikiş HumanInput node'unu da taşıyor, karışmamalı."""
    value = {"type": "human_input", "prompt": "Onaylıyor musun?", "decisions": ["Evet", "Hayır"]}

    yielded, new_messages = await _collect(value)

    packet = _one_packet(yielded)
    assert packet["type"] == "human_input"
    assert packet["prompt"] == "Onaylıyor musun?"
    assert packet["decisions"] == ["Evet", "Hayır"]
    assert new_messages == []


@pytest.mark.asyncio
async def test_a_plain_string_interrupt_becomes_an_ai_message():
    """Tanınmayan şekil paket olmuyor; sıradan bir AI mesajı olarak akıyor."""
    yielded, new_messages = await _collect("düz metin bir prompt")

    assert yielded == []
    assert len(new_messages) == 1
    assert isinstance(new_messages[0], AIMessage)
    assert new_messages[0].content == "düz metin bir prompt"
