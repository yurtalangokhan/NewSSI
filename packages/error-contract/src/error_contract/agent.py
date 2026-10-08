from .exceptions import ApplicationError


class AgentError(ApplicationError, RuntimeError):
    """Base class for agent-service failures that keep legacy constructors."""

    code = "agent.error"
    message_key = "errors.agent.error"
    status_code = 500

    def __init__(self, message: str | None = None, **kwargs) -> None:
        kwargs.setdefault("code", self.code)
        kwargs.setdefault("message_key", self.message_key)
        super().__init__(message=message, **kwargs)


class InvalidQuestionsError(AgentError):
    code = "agent.invalid_questions"
    message_key = "errors.agent.invalid_questions"
    status_code = 422


class AgentNotFoundError(AgentError):
    code = "agent.not_found"
    message_key = "errors.agent.not_found"
    status_code = 404


InvalidQuestions = InvalidQuestionsError


class GraphBuilderError(AgentError):
    code = "agent.graph_build_failed"
    message_key = "errors.agent.graph_build_failed"


class AgentClientError(AgentError):
    code = "agent.client_failed"
    message_key = "errors.agent.client_failed"
    status_code = 502


class AgentPermissionError(AgentError):
    code = "agent.permission_denied"
    message_key = "errors.agent.permission_denied"
    status_code = 403

    def __init__(self, action: str, agent_id: str | None = None) -> None:
        self.action = action
        self.agent_id = agent_id
        message = f"Permission denied: {action}"
        if agent_id:
            message = f"{message} on agent '{agent_id}'"
        super().__init__(message)


class AgentExpansionError(AgentError):
    code = "agent.expansion_failed"
    message_key = "errors.agent.expansion_failed"


class MCPAuthError(AgentError):
    code = "agent.mcp_auth_failed"
    message_key = "errors.agent.mcp_auth_failed"
    status_code = 401


__all__ = [
    "AgentClientError",
    "AgentError",
    "AgentExpansionError",
    "AgentPermissionError",
    "AgentNotFoundError",
    "GraphBuilderError",
    "InvalidQuestions",
    "InvalidQuestionsError",
    "MCPAuthError",
]
