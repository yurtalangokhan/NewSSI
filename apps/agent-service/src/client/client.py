from collections.abc import AsyncGenerator, Generator
import json
from typing import Any

from config_manager import env
from error_contract.agent import AgentClientError
import httpx
from pydantic import ValidationError

from core.http import outbound
from core.http.application_response import read_response_model
from schemas.agents import ServiceMetadata
from schemas.chat import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    Feedback,
    StreamInput,
    UserInput,
)


class AgentClient:
    """Client for interacting with the agent service."""

    def __init__(
        self,
        base_url: str | None = None,
        agent: str | None = None,
        timeout: float | None = None,
        get_info: bool = True,
    ) -> None:
        """
        Initialize the client.

        Args:
            base_url (str, optional): The base URL of the agent service. If None,
                reads from AGENT_SERVICE_URL or BASE_URL environment variables.
            agent (str): The name of the default agent to use.
            timeout (float, optional): The timeout for requests.
            get_info (bool, optional): Whether to fetch agent information on init.
                Default: True
        """
        resolved_url = base_url or env.AGENT_SERVICE_URL
        if not resolved_url:
            raise ValueError("AGENT_SERVICE_URL environment variable or base_url argument is required")
        self.base_url = resolved_url.rstrip("/")
        self.auth_secret = env.AUTHENTICATION_SECRET or ""
        self.timeout = timeout
        self.info: ServiceMetadata | None = None
        self.agent: str | None = None
        if get_info:
            self.retrieve_info()
        if agent:
            self.update_agent(agent)

    @property
    def _headers(self) -> dict[str, str]:
        headers = {}
        if self.auth_secret:
            headers["Authorization"] = f"Bearer {self.auth_secret}"
        return headers

    def retrieve_info(self) -> None:
        try:
            response = outbound.get_sync_client(outbound.EXTERNAL).get(
                f"{self.base_url}/agents/info",
                headers=self._headers,
                timeout=self.timeout,
            )
            payload = read_response_model(response)
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error getting service info: {e}") from e

        self.info = ServiceMetadata.model_validate(payload)
        if not self.agent or self.agent not in [a.key for a in self.info.agents]:
            self.agent = self.info.default_agent

    def update_agent(self, agent: str, verify: bool = True) -> None:
        if verify:
            if not self.info:
                self.retrieve_info()
            agent_keys = [a.key for a in self.info.agents]  # type: ignore[union-attr]
            if agent not in agent_keys:
                raise AgentClientError(f"Agent {agent} not found in available agents: {', '.join(agent_keys)}")
        self.agent = agent

    async def ainvoke(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """
        Invoke the agent asynchronously. Only the final message is returned.

        Args:
            message (str): The message to send to the agent
            model (str, optional): LLM model to use for the agent
            thread_id (str, optional): Thread ID for continuing a conversation
            user_id (str, optional): User ID for continuing a conversation across multiple threads
            agent_config (dict[str, Any], optional): Additional configuration to pass through to the agent

        Returns:
            AnyMessage: The response from the agent
        """
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = UserInput(message=message)
        if thread_id:
            request.thread_id = thread_id
        if model:
            request.model = model  # type: ignore[assignment]
        if agent_config:
            request.agent_config = agent_config
        if user_id:
            request.user_id = user_id
        try:
            response = await outbound.request(
                outbound.EXTERNAL,
                "POST",
                f"{self.base_url}/agents/{self.agent}/invoke",
                timeout=self.timeout,
                json=request.model_dump(),
                headers=self._headers,
            )
            payload = read_response_model(response)
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e

        return ChatMessage.model_validate(payload)

    def invoke(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """
        Invoke the agent synchronously. Only the final message is returned.

        Args:
            message (str): The message to send to the agent
            model (str, optional): LLM model to use for the agent
            thread_id (str, optional): Thread ID for continuing a conversation
            user_id (str, optional): User ID for continuing a conversation across multiple threads
            agent_config (dict[str, Any], optional): Additional configuration to pass through to the agent

        Returns:
            ChatMessage: The response from the agent
        """
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = UserInput(message=message)
        if thread_id:
            request.thread_id = thread_id
        if model:
            request.model = model  # type: ignore[assignment]
        if agent_config:
            request.agent_config = agent_config
        if user_id:
            request.user_id = user_id
        try:
            response = outbound.get_sync_client(outbound.EXTERNAL).post(
                f"{self.base_url}/agents/{self.agent}/invoke",
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
            payload = read_response_model(response)
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e

        return ChatMessage.model_validate(payload)

    def _parse_stream_line(self, line: str) -> ChatMessage | str | None:
        line = line.strip()
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                return None
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError as e:
                raise AgentClientError("Server returned invalid JSON") from e
            match parsed["type"]:
                case "message":
                    # Convert the JSON formatted message to an AnyMessage
                    try:
                        return ChatMessage.model_validate(parsed["content"])
                    except (ValidationError, TypeError) as e:
                        raise AgentClientError("Server returned invalid message") from e
                case "token":
                    # Yield the str token directly
                    return parsed["content"]
                case "error":
                    error_msg = "Error: " + parsed["content"]
                    return ChatMessage(type="ai", content=error_msg)
        return None

    def stream(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
        stream_tokens: bool = True,
    ) -> Generator[ChatMessage | str, None, None]:
        """
        Stream the agent's response synchronously.

        Each intermediate message of the agent process is yielded as a ChatMessage.
        If stream_tokens is True (the default value), the response will also yield
        content tokens from streaming models as they are generated.

        Args:
            message (str): The message to send to the agent
            model (str, optional): LLM model to use for the agent
            thread_id (str, optional): Thread ID for continuing a conversation
            user_id (str, optional): User ID for continuing a conversation across multiple threads
            agent_config (dict[str, Any], optional): Additional configuration to pass through to the agent
            stream_tokens (bool, optional): Stream tokens as they are generated
                Default: True

        Returns:
            Generator[ChatMessage | str, None, None]: The response from the agent
        """
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = StreamInput(message=message, stream_tokens=stream_tokens)
        if thread_id:
            request.thread_id = thread_id
        if user_id:
            request.user_id = user_id
        if model:
            request.model = model  # type: ignore[assignment]
        if agent_config:
            request.agent_config = agent_config
        try:
            # The shared sync client stays open; only the response closes.
            client = outbound.get_sync_client(outbound.EXTERNAL)
            with client.stream(
                "POST",
                f"{self.base_url}/agents/{self.agent}/stream",
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.strip():
                        parsed = self._parse_stream_line(line)
                        if parsed is None:
                            break
                        yield parsed
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e

    async def astream(
        self,
        message: str,
        model: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
        stream_tokens: bool = True,
    ) -> AsyncGenerator[ChatMessage | str, None]:
        """
        Stream the agent's response asynchronously.

        Each intermediate message of the agent process is yielded as an AnyMessage.
        If stream_tokens is True (the default value), the response will also yield
        content tokens from streaming modelsas they are generated.

        Args:
            message (str): The message to send to the agent
            model (str, optional): LLM model to use for the agent
            thread_id (str, optional): Thread ID for continuing a conversation
            user_id (str, optional): User ID for continuing a conversation across multiple threads
            agent_config (dict[str, Any], optional): Additional configuration to pass through to the agent
            stream_tokens (bool, optional): Stream tokens as they are generated
                Default: True

        Returns:
            AsyncGenerator[ChatMessage | str, None]: The response from the agent
        """
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        request = StreamInput(message=message, stream_tokens=stream_tokens)
        if thread_id:
            request.thread_id = thread_id
        if model:
            request.model = model  # type: ignore[assignment]
        if agent_config:
            request.agent_config = agent_config
        if user_id:
            request.user_id = user_id
        try:
            # Streaming keeps the shared client open; only the response closes.
            client = outbound.get_client(outbound.EXTERNAL)
            async with client.stream(
                "POST",
                f"{self.base_url}/agents/{self.agent}/stream",
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        parsed = self._parse_stream_line(line)
                        if parsed is None:
                            break
                        # Don't yield empty string tokens as they cause generator issues
                        if parsed != "":
                            yield parsed
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e

    async def acreate_feedback(self, run_id: str, key: str, score: float, kwargs: dict[str, Any] | None = None) -> None:
        """
        Create a feedback record for a run.

        This is a simple wrapper for the LangSmith create_feedback API, so the
        credentials can be stored and managed in the service rather than the client.
        See: https://api.smith.langchain.com/redoc#tag/feedback/operation/create_feedback_api_v1_feedback_post
        """
        if kwargs is None:
            kwargs = {}
        request = Feedback(run_id=run_id, key=key, score=score, kwargs=kwargs)
        try:
            response = await outbound.request(
                outbound.EXTERNAL,
                "POST",
                f"{self.base_url}/agents/feedback",
                timeout=self.timeout,
                json=request.model_dump(),
                headers=self._headers,
            )
            response.raise_for_status()
            read_response_model(response)
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e

    def get_history(self, thread_id: str) -> ChatHistory:
        """
        Get chat history.

        Args:
            thread_id (str, optional): Thread ID for identifying a conversation
        """
        request = ChatHistoryInput(thread_id=thread_id)
        try:
            response = outbound.get_sync_client(outbound.EXTERNAL).post(
                f"{self.base_url}/agents/history",
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
            payload = read_response_model(response)
        except httpx.HTTPError as e:
            raise AgentClientError(f"Error: {e}") from e

        return ChatHistory.model_validate(payload)
