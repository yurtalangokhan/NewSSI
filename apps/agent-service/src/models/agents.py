from pydantic import BaseModel, Field

from models.llm import ModelName


class AgentInfo(BaseModel):
    """Info about an available agent."""

    key: str = Field(description="Agent key.", examples=["research-assistant"])
    description: str = Field(
        description="Description of the agent.",
        examples=["A research assistant for generating research papers."],
    )


class ServiceMetadata(BaseModel):
    """Metadata about the service including available agents and models."""

    agents: list[AgentInfo] = Field(description="List of available agents.")
    models: list[ModelName] = Field(description="List of available LLMs.")
    default_agent: str = Field(
        description="Default agent used when none is specified.",
        examples=["research-assistant"],
    )
    default_model: str | None = Field(
        default=None,
        description="Default model used when none is specified.",
    )
