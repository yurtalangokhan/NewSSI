"""
Configurable MCP Agent.
A simple agent that allows users to configure system prompt and select MCP tools.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from agents.lazy_agent import LazyLoadingAgent
from core import get_model, settings

logger = logging.getLogger(__name__)

# Default system prompt
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant. 
You have access to various tools that help you accomplish tasks.
Always be helpful, accurate, and provide clear explanations."""


class ConfigurableMCPAgent(LazyLoadingAgent):
    """
    A configurable agent with MCP tool support.
    
    Configuration (via agent_config):
        - system_prompt: Custom system prompt for the agent
        - mcp_tools: List of MCP tool names this agent can use
    """
    
    def __init__(self) -> None:
        super().__init__()
        self._default_graph: Optional[CompiledStateGraph] = None
        self._mcp_tools: Dict[str, BaseTool] = {}
    
    @property
    def name(self) -> str:
        return "configurable-mcp-agent"
    
    @property
    def description(self) -> str:
        return "A configurable agent with custom system prompt and MCP tool selection"
    
    async def load(self) -> None:
        """Create a default graph and load MCP tools."""
        if self._loaded:
            return
        
        try:
            # Load MCP tools
            await self._load_mcp_tools()
            
            # Create default graph
            self._default_graph = self._create_agent_graph(
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                mcp_tool_names=[]
            )
            self._graph = self._default_graph
            self._loaded = True
            
            logger.info(f"Configurable MCP Agent initialized with {len(self._mcp_tools)} MCP tools available")
            
        except Exception as e:
            logger.error(f"Failed to initialize Configurable MCP Agent: {e}")
            # Create a minimal fallback graph
            self._default_graph = self._create_agent_graph(
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                mcp_tool_names=[]
            )
            self._graph = self._default_graph
            self._loaded = True
            logger.warning("Using fallback graph without MCP tools")
    
    async def _load_mcp_tools(self, mcp_url: Optional[str] = None) -> None:
        """Load tools from MCP server."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            
            url = mcp_url or os.environ.get("MCP_SERVER_URL", "http://mcp-server:8001/mcp")
            
            client = MultiServerMCPClient(
                connections={
                    "mcp-tools": {
                        "transport": "streamable_http",
                        "url": url,
                    }
                }
            )
            
            # New API: directly call get_tools() without context manager
            tools = await client.get_tools()
            
            # Store tools by name for easy lookup
            for tool in tools:
                self._mcp_tools[tool.name] = tool
            
            logger.info(f"Loaded {len(tools)} MCP tools: {list(self._mcp_tools.keys())}")
            
        except Exception as e:
            logger.warning(f"Could not load MCP tools: {e}")
    
    def _create_agent_graph(
        self,
        system_prompt: str,
        mcp_tool_names: List[str],
        model_name: Optional[str] = None,
        checkpointer: Optional[Any] = None,
    ) -> CompiledStateGraph:
        """
        Create an agent graph with the specified configuration.
        
        Args:
            system_prompt: System prompt for the agent
            mcp_tool_names: List of MCP tool names to use
            model_name: Optional model override
            checkpointer: Optional checkpointer for persistence
        
        Returns:
            Compiled agent graph
        """
        model = get_model(model_name or settings.DEFAULT_MODEL)
        
        # Collect selected tools
        agent_tools = []
        for tool_name in mcp_tool_names:
            if tool_name in self._mcp_tools:
                agent_tools.append(self._mcp_tools[tool_name])
            else:
                logger.warning(f"MCP tool '{tool_name}' not found")
        
        # Create the agent
        agent = create_react_agent(
            model=model,
            tools=agent_tools,
            name="configurable-agent",
            prompt=SystemMessage(content=system_prompt),
            checkpointer=checkpointer,
        )
        
        return agent
    
    async def ainvoke(
        self, 
        input: Any, 
        config: Optional[RunnableConfig] = None,
        checkpointer: Optional[Any] = None,
        **kwargs: Any
    ) -> Any:
        """
        Async invoke with dynamic configuration support.
        
        Checks for custom configuration in the config and creates
        a customized graph if needed.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)
        
        # Get configuration
        configurable = (config or {}).get("configurable", {})
        
        system_prompt = configurable.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        mcp_tool_names = configurable.get("mcp_tools", [])
        model_name = configurable.get("model")
        mcp_url = configurable.get("mcp_url")
        
        # Reload MCP tools if URL changed
        if mcp_url and mcp_url != os.environ.get("MCP_SERVER_URL", "http://mcp-server:8001/mcp"):
            self._mcp_tools = {}
            await self._load_mcp_tools(mcp_url)
        
        # If custom configuration provided, create a custom graph
        if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
            graph = self._create_agent_graph(
                system_prompt=system_prompt,
                mcp_tool_names=mcp_tool_names,
                model_name=model_name,
                checkpointer=checkpointer,
            )
            result = await graph.ainvoke(input, config=config, **kwargs)
        else:
            result = await self._graph.ainvoke(input, config=config, **kwargs)

        # Save memories from output
        await self._save_memory_from_output(result, original_messages, memories, user_id, config)
        return result
    
    async def astream(
        self, 
        input: Any, 
        config: Optional[RunnableConfig] = None,
        checkpointer: Optional[Any] = None,
        **kwargs: Any
    ):
        """
        Async stream with dynamic configuration support.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)
        
        # Get configuration
        configurable = (config or {}).get("configurable", {})
        
        system_prompt = configurable.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        mcp_tool_names = configurable.get("mcp_tools", [])
        model_name = configurable.get("model")
        mcp_url = configurable.get("mcp_url")
        
        # Reload MCP tools if URL changed
        if mcp_url and mcp_url != os.environ.get("MCP_SERVER_URL", "http://mcp-server:8001/mcp"):
            self._mcp_tools = {}
            await self._load_mcp_tools(mcp_url)
        
        # If custom configuration provided, create a custom graph
        collected_output = None
        if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
            graph = self._create_agent_graph(
                system_prompt=system_prompt,
                mcp_tool_names=mcp_tool_names,
                model_name=model_name,
                checkpointer=checkpointer,
            )
            async for chunk in graph.astream(input, config=config, **kwargs):
                collected_output = chunk
                yield chunk
        else:
            # Use default graph
            async for chunk in self._graph.astream(input, config=config, **kwargs):
                collected_output = chunk
                yield chunk

        # Save memories from the last output chunk
        if collected_output is not None:
            await self._save_memory_from_output(
                collected_output, original_messages, memories, user_id, config
            )
    
    async def astream_events(
        self, 
        input: Any, 
        config: Optional[RunnableConfig] = None,
        version: str = "v2",
        checkpointer: Optional[Any] = None,
        **kwargs: Any
    ):
        """
        Async stream events with dynamic configuration support.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)
        
        # Get configuration
        configurable = (config or {}).get("configurable", {})
        
        system_prompt = configurable.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        mcp_tool_names = configurable.get("mcp_tools", [])
        model_name = configurable.get("model")
        mcp_url = configurable.get("mcp_url")
        
        # Reload MCP tools if URL changed
        if mcp_url and mcp_url != os.environ.get("MCP_SERVER_URL", "http://mcp-server:8001/mcp"):
            self._mcp_tools = {}
            await self._load_mcp_tools(mcp_url)
        
        # If custom configuration provided, create a custom graph
        if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
            graph = self._create_agent_graph(
                system_prompt=system_prompt,
                mcp_tool_names=mcp_tool_names,
                model_name=model_name,
                checkpointer=checkpointer,
            )
            async for event in graph.astream_events(input, config=config, version=version, **kwargs):
                yield event
        else:
            # Use default graph
            async for event in self._graph.astream_events(input, config=config, version=version, **kwargs):
                yield event

        # Save memories after streaming completes
        if configurable.get("long_term_memory", False) and user_id:
            try:
                store = self._get_langgraph_store()
                if store:
                    from core import get_model, settings as core_settings
                    model = get_model(configurable.get("model", core_settings.DEFAULT_MODEL))
                    from memory.long_term import extract_and_save_memories
                    await extract_and_save_memories(
                        store, user_id, original_messages, model, memories
                    )
            except Exception as e:
                logger.warning(f"[ConfigurableMCPAgent] Memory save after stream_events failed: {e}")


# Create the agent instance
configurable_mcp_agent = ConfigurableMCPAgent()
