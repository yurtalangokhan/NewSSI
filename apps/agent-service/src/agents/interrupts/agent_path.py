"""Duraklatan alt agent zinciri.

Supervisor ya da pipeline altında kullanıcı, hangi alt agent'ın konuştuğunu
görmeden karar veremez: "bir e-posta gönderilecek" ile "Fatura Uzmanı bir
e-posta gönderecek" farklı kararlar doğurur. Aynı şey soru sorarken de
geçerli — soruyu kimin sorduğu cevabı değiştirir.

LangGraph alt graflara "node_adı:uuid" biçiminde bir checkpoint namespace
veriyor ve iç içe grafiklerde bunları "|" ile zincirliyor. Ad kısmı bize
lazım olan tek şey.

Namespace'in nereden okunduğu ölçüldü (D5): ``Runtime`` nesnesi config
taşımıyor, ama ``langgraph.config.get_config()`` çalışma anında taşıyor.
Zincirin son halkası çağıranın kendi node'u (ör. ``<Middleware>.after_model``)
olduğu için altyapı halkaları ayıklanıyor.
"""

from typing import Any

_NS_SEPARATOR = "|"
_NAME_SEPARATOR = ":"

# Kullanıcıya gösterilecek bir ad olmayan halkalar. Middleware node'ları
# "<SınıfAdı>.<hook>" biçiminde adlandırılıyor; nokta bu yüzden yeterli bir
# ayırt edici. Grafın kendi giriş/çıkış node'ları da elenir.
_INFRA_NODE_NAMES = frozenset({"model", "tools", "agent", "__start__", "__end__"})


def _is_infrastructure(name: str) -> bool:
    return "." in name or name in _INFRA_NODE_NAMES


def _namespace_of(runtime: Any) -> str | None:
    config = getattr(runtime, "config", None)
    if not config:
        try:
            from langgraph.config import get_config

            config = get_config()
        except Exception:
            return None
    return ((config or {}).get("configurable") or {}).get("checkpoint_ns")


def resolve_agent_path(runtime: Any, fallback: str | None = None) -> list[str]:
    ns = _namespace_of(runtime)

    if not ns:
        return [fallback] if fallback else []

    names = [
        segment.split(_NAME_SEPARATOR, 1)[0].strip()
        for segment in str(ns).split(_NS_SEPARATOR)
        if segment.strip()
    ]
    names = [n.replace("_", " ").strip() for n in names if n and not _is_infrastructure(n)]
    return names or ([fallback] if fallback else [])
