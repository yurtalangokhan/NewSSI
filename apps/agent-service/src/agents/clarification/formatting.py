"""Resume değerini modelin okuyacağı metne ve saklanacak artifact'a çevirir.

İki ayrı çıktı olmasının sebebi §3.5: ``content`` modelin okuduğu, ``artifact``
geçmiş yeniden kurulurken kartı çizmek için makinenin okuduğu. Geçmiş tarafı
metni ASLA ayrıştırmıyor — ayrıştırma, modelin metni biraz farklı yazdığı ilk
günde sessizce bozulurdu.

Resume değeri dış dünyadan (tarayıcıdan) geliyor, dolayısıyla burada hiçbir
şekil garanti sayılmıyor.
"""

from typing import Any

_DEFERRED = "(the user left this decision to you)"


def _as_labels(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def normalise_resume(resume: Any) -> dict[str, Any]:
    """Her resume'u iki şekilden birine indirger: cevaplandı ya da cevaplanmadı."""
    if not isinstance(resume, dict):
        return {"answered": False, "text": str(resume) if resume else ""}
    if not resume.get("answered"):
        return {"answered": False, "text": str(resume.get("text") or "")}

    raw = resume.get("answers")
    answers = (
        {str(header): _as_labels(value) for header, value in raw.items()}
        if isinstance(raw, dict)
        else {}
    )
    return {"answered": True, "answers": answers}


def format_resume(questions: list[dict[str, Any]], resume: Any) -> str:
    normalised = normalise_resume(resume)

    if not normalised["answered"]:
        said = normalised["text"]
        if not said:
            return (
                "The user did not answer the questions and said nothing else. "
                "Continue with your best judgement and state your assumptions."
            )
        return (
            "The user did not answer the questions. They said this instead:\n"
            f'"{said}"\n'
            "Treat that as their instruction; do not assume it answers any of the questions."
        )

    answers = normalised["answers"]
    # Soru sırası korunuyor: model soruları bir sebeple o sırada sordu.
    lines = [
        f"{q['header']}: {', '.join(_as_labels(answers.get(q['header']))) or _DEFERRED}"
        for q in questions
    ]
    return "The user answered:\n" + "\n".join(lines)
