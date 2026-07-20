from pydantic import BaseModel, Field


class PersonaUpsertRequest(BaseModel):
    name: str
    description: str
    system_prompt: str = ""
    task_prompt: str = ""
    datetime_aware: bool = True
    document_set_ids: list = Field(default_factory=list)
    is_public: bool = True
    llm_model_provider_override: str | None = None
    llm_model_version_override: str | None = None
    starter_messages: list | None = None
    users: list = Field(default_factory=list)
    groups: list = Field(default_factory=list)
    tool_ids: list = Field(default_factory=list)
    remove_image: bool = False
    uploaded_image_id: str | None = None
    icon_name: str | None = None
    search_start_date: str | None = None
    featured: bool = False
    display_priority: int | None = None
    label_ids: list = Field(default_factory=list)
    user_file_ids: list = Field(default_factory=list)
    replace_base_system_prompt: bool = False
    hierarchy_node_ids: list = Field(default_factory=list)
    document_ids: list = Field(default_factory=list)
    base_agent: str | None = None
    graph_schema: str = "zero_shot"
    brain_type: str = "llm"
    memory_type: str = "none"
    sub_agent_ids: list[str] = Field(default_factory=list)
    sub_agents: list[dict] = Field(default_factory=list)
    supervisor_prompt: str | None = None
    stages: list[dict] = Field(default_factory=list)
    pipeline_prompt: str | None = None
    reflection_prompt: str | None = None
    max_iterations: int = 3
    mcp_tools: list[str] = Field(default_factory=list)
    rag_config: dict | None = None
    long_term_memory: bool = False
