"""`ask_user` için SSE / geçmiş paketleri.

İki paket var ve ikisi de aynı kartı anlatıyor:

- ``user_clarification`` — sorular; kart cevap bekliyor
- ``user_clarification_answered`` — cevaplar; kart yerinde kilitleniyor

``v`` alanı tanınmayan bir sürümde kartın "bu sürümde gösterilemiyor" demesi
için var. Onay kapısındakinden daha yumuşak bir gerekçe: burada çizilmeyen
kart yalnızca bir soruyu gizler, geri alınamaz bir eylem tetiklemez.

GEÇMİŞ TARAFI: paketler METİN AYRIŞTIRARAK değil, checkpoint'in kendi
yapılandırılmış verisinden kuruluyor — sorular ``tool_call.args``'tan,
cevaplar ``ToolMessage.artifact``'tan (§3.5).
"""

from typing import Any

from agents.clarification.formatting import normalise_resume
from agents.clarification.schema import InvalidQuestions, validate_questions
from agents.clarification.tool import PAYLOAD_VERSION

CLARIFICATION_PACKET = "user_clarification"
ANSWERED_PACKET = "user_clarification_answered"


def clarification_packet(
    request_id: str,
    questions: list[dict[str, Any]],
    agent_path: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": CLARIFICATION_PACKET,
        "v": PAYLOAD_VERSION,
        "request_id": request_id,
        "questions": questions,
        "agent_path": agent_path or [],
    }


def answered_packet(request_id: str, resume: Any) -> dict[str, Any]:
    normalised = normalise_resume(resume)
    packet = {
        "type": ANSWERED_PACKET,
        "v": PAYLOAD_VERSION,
        "request_id": request_id,
        "answered": normalised["answered"],
    }
    if normalised["answered"]:
        packet["answers"] = normalised["answers"]
    else:
        packet["text"] = normalised["text"]
    return packet


def packet_from_interrupt(value: Any, request_id: str) -> dict[str, Any] | None:
    """Bekleyen bir interrupt payload'ı → canlı/yeniden yükleme paketi."""
    if not isinstance(value, dict):
        return None
    return clarification_packet(
        request_id,
        value.get("questions") or [],
        value.get("agent_path"),
    )


def packets_for_history(
    call_id: str,
    args: Any,
    artifact: Any,
) -> list[dict[str, Any]] | None:
    """Cevaplanmış bir `ask_user` çağrısı → kart + kilit paketi çifti.

    ``None`` dönmesi "bu çağrı için geçmişte hiçbir şey çizme" demek. İki
    durumda olur ve ikisi de doğru: model geçersiz argüman gönderdiyse
    kullanıcı zaten hiçbir şey görmedi, ve ``artifact`` bir hata taşıyorsa
    duraklama hiç açılmadı.

    Bozuk ama hatasız bir artifact kartı yine de çizdiriyor (E21): sorular
    görünür, seçimler boş kalır. Eksik çizmek, hiç çizmemekten iyi bir
    gerileme — kullanıcı ne sorulduğunu yine görür.
    """
    if isinstance(artifact, dict) and "error" in artifact:
        return None

    raw = args.get("questions") if isinstance(args, dict) else None
    try:
        questions = validate_questions(raw)
    except InvalidQuestions:
        return None

    return [
        clarification_packet(call_id, questions),
        answered_packet(call_id, artifact),
    ]
