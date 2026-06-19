from enum import Enum

from langchain_core.messages import AnyMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

from core.env import env
from core.logger import get_logger

logger = get_logger(__name__)


class SafetyAssessment(Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"
    ERROR = "error"


class LlamaGuardOutput(BaseModel):
    safety_assessment: SafetyAssessment = Field(description="The safety assessment of the content.")
    unsafe_categories: list[str] = Field(
        description="If content is unsafe, the list of unsafe categories.", default=[]
    )


llama_guard_instructions = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a safety guard for an AI assistant. Your task is to analyze user input and determine if it contains any unsafe content that could be harmful, illegal, or inappropriate.

Categories of unsafe content:
- Violence and physical harm
- Sexual content and exploitation
- Hate speech and discrimination
- Self-harm and suicide
- Harassment and bullying
- Illegal activities and drugs
- PII and privacy violations
- Medical advice and health risks
- Financial advice and scams
- Cybersecurity threats

Evaluate the conversation history and determine if the input is safe or unsafe.

Your response must be one of these exact formats:

For SAFE content:
```
safe
```

For UNSAFE content:
```
unsafe
[<category1>, <category2>, ...]
```
<|eot_id|><|start_header_id|>role<|end_header_id|>

{conversation_history}

<|eot_id|><|start_header_id|>agent<|end_header_id|>

"""


def parse_llama_guard_output(output: str) -> LlamaGuardOutput:
    lines = output.strip().split("\n")
    first_line = lines[0].strip().lower()

    if first_line == "safe":
        return LlamaGuardOutput(safety_assessment=SafetyAssessment.SAFE)
    elif first_line == "unsafe":
        categories = []
        if len(lines) > 1:
            categories = [c.strip() for c in lines[1:] if c.strip()]
        return LlamaGuardOutput(
            safety_assessment=SafetyAssessment.UNSAFE,
            unsafe_categories=categories,
        )
    else:
        return LlamaGuardOutput(safety_assessment=SafetyAssessment.ERROR)


class LlamaGuard:
    def __init__(self) -> None:
        groq_key = env.get("GROQ_API_KEY")
        if not groq_key and not env.OLLAMA_BASE_URL:
            logger.info("No GROQ_API_KEY or OLLAMA_BASE_URL, skipping LlamaGuard")
            self.model = None
            return

        if groq_key:
            model_name = "llama-guard-3-8b"
            from langchain_groq import ChatGroq

            self.model = ChatGroq(model=model_name, temperature=0.0).with_config(
                tags=["skip_stream"]
            )
        else:
            from core.llm import get_model

            # Use available Ollama model for safety checks
            # llama-guard-3-8b may not be available, fallback to default model
            model_name = env.get("LLAMA_GUARD_MODEL", "llama3.1:8b")
            try:
                self.model = get_model(model_name).with_config(tags=["skip_stream"])
            except Exception as e:
                logger.warning(
                    "Failed to load LlamaGuard model %s: %s. Skipping safety checks.", model_name, e
                )
                self.model = None
                return

        self.prompt = PromptTemplate.from_template(llama_guard_instructions)

    def _compile_prompt(self, role: str, messages: list[AnyMessage]) -> str:
        role_mapping = {"ai": "Agent", "human": "User"}
        messages_str = [
            f"{role_mapping[m.type]}: {m.content}" for m in messages if m.type in ["ai", "human"]
        ]
        conversation_history = "\n\n".join(messages_str)
        return self.prompt.format(role=role, conversation_history=conversation_history)

    def invoke(self, role: str, messages: list[AnyMessage]) -> LlamaGuardOutput:
        if self.model is None:
            return LlamaGuardOutput(safety_assessment=SafetyAssessment.SAFE)
        compiled_prompt = self._compile_prompt(role, messages)
        result = self.model.invoke([HumanMessage(content=compiled_prompt)])
        return parse_llama_guard_output(str(result.content))

    async def ainvoke(self, role: str, messages: list[AnyMessage]) -> LlamaGuardOutput:
        if self.model is None:
            return LlamaGuardOutput(safety_assessment=SafetyAssessment.SAFE)
        compiled_prompt = self._compile_prompt(role, messages)
        result = await self.model.ainvoke([HumanMessage(content=compiled_prompt)])
        return parse_llama_guard_output(str(result.content))
