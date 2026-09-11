"""Niyet netleştirme: agent kararsız kaldığında kullanıcıya şıklı soru sorar.

Onay kapısının tersi yönde çalışır: orada duraklamaya platform karar verir
(model kandırılabilir), burada duraklamaya model karar verir — kararsız
olduğunu yalnızca o bilebilir. İkisi aynı interrupt boru hattını paylaşır.
"""

ASK_USER_TOOL_NAME = "ask_user"


def is_clarification_tool(tool_name: str | None) -> bool:
    """Bu araç akış/geçmiş katmanlarında genel araç kartı ÜRETMEZ.

    Kendi kartı var; genel kartı da çizmek aynı soruyu iki kez gösterirdi
    (tasarım E4). ``is_document_tool`` ile aynı rolü oynuyor.
    """
    return tool_name == ASK_USER_TOOL_NAME
