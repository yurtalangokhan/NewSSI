"""Aracın hangi graflara eklendiği — ve hangilerine eklenmediği.

Tek koşul checkpointer, ve o koşul iki kararı birden veriyor: kalıcılık
olmadan `interrupt()` yazacak yer bulamaz (E13), ve flow canvas her zaman
``checkpointer=None`` ile inşa ediliyor, dolayısıyla flow'lar aracı hiç
görmez (K3, E14).
"""

from agents.graphs.builder import GraphBuilder


def _builder(checkpointer):
    return GraphBuilder(checkpointer=checkpointer)


def test_a_persistent_chat_agent_gets_the_tool_and_the_prompt():
    tools, prompt = _builder(object())._attach_clarification([], "Sen bir asistansın.")
    assert [t.name for t in tools] == ["ask_user"]
    assert "ask_user" in prompt and "Sen bir asistansın." in prompt


def test_without_a_checkpointer_the_tool_is_not_offered_at_all():
    """E13: olmayan bir aracı model çağıramaz, "sordum ama cevap gelmedi" doğmaz."""
    tools, prompt = _builder(None)._attach_clarification([], "Sen bir asistansın.")
    assert tools == []
    assert prompt == "Sen bir asistansın."


def test_existing_tools_are_kept():
    class _T:
        name = "create_document"

    tools, _ = _builder(object())._attach_clarification([_T()], "x")
    assert [t.name for t in tools] == ["create_document", "ask_user"]


def test_the_call_alone_guard_follows_the_tool_onto_the_react_agent_paths():
    """Bulgu #1: ``create_react_agent``'in middleware yuvası yok.

    ``_build_react`` guard'ı ``AskUserAloneMiddleware`` olarak alıyor; alt
    agent ve plan-execute grafları ``create_react_agent`` kullanıyor ve aynı
    guard'ı ``post_model_hook`` olarak almalı — checkpointer varsa araç da
    var, guard da olmalı; yoksa ikisi de yok.
    """
    from agents.clarification.middleware import ask_user_alone_post_model_hook

    assert _builder(object())._clarification_post_model_hook() is ask_user_alone_post_model_hook
    assert _builder(None)._clarification_post_model_hook() is None


def test_the_react_agent_builds_pass_the_hook_through():
    """Guard'ın kod içinde gerçekten bağlandığını sabitler."""
    from pathlib import Path

    source = Path("src/agents/graphs/builder.py").read_text()
    # Alt agent grafı + plan-execute grafı: iki create_react_agent çağrısı da
    # guard'ı geçiriyor.
    assert source.count("post_model_hook=self._clarification_post_model_hook()") == 2


def test_every_flow_canvas_build_passes_no_checkpointer():
    """K3/E14'ün dayanağı: flow tarafı GraphBuilder'ı hep checkpointer=None kuruyor.

    Bu satır kırılırsa flow'lar sessizce duraklayabilir hale gelir — ve
    RunFlow alt çalışmaları duraklayamaz.
    """
    import re
    from pathlib import Path

    source = Path("src/agents/graphs/flow_builder.py").read_text()
    constructions = re.findall(r"GraphBuilder\(\s*(.*?)\)", source, re.S)
    assert constructions
    assert all("checkpointer=None" in c for c in constructions)
