"""Onayı isteyen alt agent zincirinin çözülmesi.

D5 ölçümü (Faz 1): ``runtime`` nesnesi config taşımıyor — üzerinde yalnızca
context/store/stream_writer var. Namespace ``langgraph.config.get_config()``
üzerinden okunabiliyor ve şu biçimde geliyor:

    "ApprovalGateMiddleware.after_model:93db9129-..."

yani zincirin son halkası kapının KENDİ node'u, agent adı değil. İç içe
grafiklerde bunun önüne alt graf node'ları "|" ile ekleniyor. Çözücü bu
yüzden kendi altyapı halkalarını atıyor ve geriye kalan ad zincirini
döndürüyor.
"""

from types import SimpleNamespace

from agents.interrupts.agent_path import resolve_agent_path


def _runtime(ns: str | None):
    return SimpleNamespace(config={"configurable": {"checkpoint_ns": ns}} if ns is not None else {})


def test_single_agent_has_a_one_element_path():
    assert resolve_agent_path(_runtime(""), fallback="react-agent") == ["react-agent"]


def test_nested_namespace_becomes_an_ordered_path():
    """LangGraph namespace'i 'node:uuid|node:uuid' şeklinde zincirliyor.

    uuid kısmı görüntülenecek bir şey değil; sadece node adı anlamlı.
    """
    ns = "Destek_Supervisor:9f1c|Fatura_Uzmani:2ab7"
    assert resolve_agent_path(_runtime(ns)) == ["Destek Supervisor", "Fatura Uzmani"]


def test_the_gates_own_node_is_not_part_of_the_path():
    """Kapının kendi node'u kullanıcıya gösterilecek bir ad değil."""
    ns = "Fatura_Uzmani:2ab7|ApprovalGateMiddleware.after_model:93db"
    assert resolve_agent_path(_runtime(ns)) == ["Fatura Uzmani"]


def test_a_path_of_only_infrastructure_falls_back():
    ns = "ApprovalGateMiddleware.after_model:93db"
    assert resolve_agent_path(_runtime(ns), fallback="react-agent") == ["react-agent"]


def test_missing_namespace_falls_back():
    assert resolve_agent_path(_runtime(None), fallback="react-agent") == ["react-agent"]


def test_missing_namespace_and_no_fallback_is_empty_not_none():
    """Boş liste, istemcide 'rozet gösterme' demek; None ise JSON'da patlar."""
    assert resolve_agent_path(_runtime(None)) == []
