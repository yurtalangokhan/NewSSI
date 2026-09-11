"""`ask_user`: modelin kararsız kaldığında kullanıcıya soru sorduğu araç.

Duraklama ``interrupt()`` ile: araç sonuç döndürmüyor, çalışma checkpoint'te
duruyor ve kullanıcı cevaplayınca aynı yerden devam ediyor (§3.1).

ÖLÇÜLMÜŞ KISIT (§3.2): resume sonrası node BAŞINDAN koşuyor, yani
``interrupt()`` çağrısından önceki her şey ikinci kez çalışıyor. Aşağıdaki
kodda oradaki tek iş payload kurmak ve o idempotent. Buraya bir günlük
satırı, bir sayaç ya da herhangi bir yan etki eklemeyin — iki kez çalışır.
"""

from typing import Any

from langchain_core.tools import BaseTool, tool
from langgraph.types import interrupt

from agents.clarification.formatting import format_resume, normalise_resume
from agents.clarification.schema import InvalidQuestions, validate_questions
from agents.interrupts.agent_path import resolve_agent_path
from agents.interrupts.classify import USER_CLARIFICATION

PAYLOAD_VERSION = 1


@tool(response_format="content_and_artifact")
async def ask_user(questions: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Ask the user to clarify an ambiguous request by choosing between options.

    The run pauses until the user answers, so call this alone — never together
    with other tool calls.

    Args:
        questions: 1-4 questions. Each is an object with:
            - `question`: the question text, in the user's language.
            - `header`: 1-3 words naming the question. Shown as a tab title and
              used as the answer key, so it must be unique within the call.
            - `options`: 2-4 objects with a `label` and a short `description`,
              in the user's language. Do not add a "you decide" option; the
              interface adds one.
            - `multiSelect`: true if more than one option may be picked.
              Defaults to false.

    Returns:
        The user's answers, or what they said instead of answering.
    """
    try:
        validated = validate_questions(questions)
    except InvalidQuestions as exc:
        # Modele dönen bir hata; düzeltip tekrar çağırabilir. Kullanıcı bunu
        # hiç görmez, çünkü duraklama hiç açılmadı.
        return (f"The call was rejected and the user was not asked. {exc}", {"error": str(exc)})

    resume = interrupt(
        {
            "type": USER_CLARIFICATION,
            "v": PAYLOAD_VERSION,
            "questions": validated,
            "agent_path": resolve_agent_path(None),
        }
    )

    return format_resume(validated, resume), normalise_resume(resume)


def get_clarification_tools() -> list[BaseTool]:
    """`get_document_tools()` ile aynı kalıp; bağlama tarafı ikisini aynı görür.

    Checkpointer yoksa araç HİÇ eklenmiyor (§5.3, E13): ``interrupt()``'ın
    yazacak yeri olmadan sessizce boş cevapla dönerdi. Olmayan bir aracı
    model çağıramaz, dolayısıyla o durum hiç doğmaz. Kontrol çağıran
    tarafta — burası neyin var olduğunu değil, ne olduğunu bilir.
    """
    return [ask_user]
