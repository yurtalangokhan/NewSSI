# Dynamic Supervisor Agents Guide

This guide explains how to use the dynamic multi-agent supervisor system in the Agent Service Toolkit.

## Overview

The system provides two types of dynamic supervisors:

1. **Flat Supervisor** (`langgraph-supervisor-agent`): Manages multiple agents working in **PARALLEL**. The supervisor delegates to one or more agents based on the request.
2. **Pipeline Supervisor** (`langgraph-supervisor-hierarchy-agent`): Executes agents in a **SEQUENTIAL** pipeline, where each stage's output feeds into the next.

## Key Difference

| Aspect | Flat Supervisor | Pipeline Supervisor |
|--------|-----------------|---------------------|
| Execution | **Parallel** - agents work simultaneously | **Sequential** - stages run one after another |
| Delegation | Supervisor chooses which agent(s) to use | All stages execute in order |
| Output | Supervisor synthesizes results | Each stage passes output to next |
| Use Case | Multiple specialists needed | Step-by-step workflows |

## Flat Supervisor (Parallel Agents)

### Use Case
When you have multiple specialized agents and want a supervisor to:
- Analyze user requests
- Delegate to the most appropriate agent(s) **in parallel**
- Combine results from multiple agents
- Provide unified responses

### Configuration

In the UI, select the "Flat Supervisor" agent and configure:

| Field | Description |
|-------|-------------|
| **Model** | The LLM model to use for the supervisor |
| **Supervisor System Prompt** | Custom prompt that tells the supervisor how to coordinate agents |
| **Sub-Agents** | Configure agents with name, system prompt, and MCP tools |

### Sub-Agent Configuration

Each sub-agent has:

| Field | Description |
|-------|-------------|
| **Name** | Agent identifier (e.g., "pdf-analyzer", "web-researcher") |
| **System Prompt** | Instructions for this agent |
| **MCP Tools** | Select which MCP tools this agent can use |

### Example: PDF Analysis + Web Research

```json
{
  "model": "claude-sonnet-4-20250514",
  "supervisor_prompt": "You are a research coordinator. Delegate PDF analysis to the pdf-analyzer agent and web research to the web-researcher agent. Synthesize their results.",
  "sub_agents": [
    {
      "name": "pdf-analyzer",
      "system_prompt": "You are a PDF analysis expert. Read and analyze PDF documents, extract key information, and summarize findings.",
      "mcp_tools": ["read_pdf", "search_pdf", "get_pdf_info"]
    },
    {
      "name": "web-researcher", 
      "system_prompt": "You are a web researcher. Search the internet for relevant information about topics from the PDF.",
      "mcp_tools": ["read_pdf", "tavily_search"]
    }
  ]
}
```

### How It Works

1. User sends a message (e.g., "Analyze this PDF and research the technologies mentioned")
2. Supervisor analyzes the request
3. Supervisor delegates to appropriate agent(s) - **both can run in parallel**
4. Sub-agents process their tasks (visible in the UI)
5. Supervisor synthesizes results and provides unified response

## Pipeline Supervisor (Sequential Workflow)

### Use Case
When you need a multi-stage workflow where:
- Each stage has a specific purpose
- Output from one stage feeds into the next
- Different MCP tools are needed at each stage

### Configuration

In the UI, select the "Pipeline Supervisor" agent and configure:

| Field | Description |
|-------|-------------|
| **Model** | The LLM model to use |
| **Pipeline Stages** | Array of stage configurations |
| **Retry Count** | Number of retries on stage failure |
| **On Error** | Error handling strategy (abort/skip) |

### Stage Configuration

Each pipeline stage has:

| Field | Description |
|-------|-------------|
| **Name** | Stage identifier (e.g., "enricher", "implementer") |
| **System Prompt** | Instructions for this stage's agent |
| **MCP Tools** | Select which MCP tools this stage can use |

### Example: Project Development Pipeline

```json
{
  "model": "claude-sonnet-4-20250514",
  "pipeline_stages": [
    {
      "name": "enricher",
      "system_prompt": "You are a project analyst. Take the user's project idea and expand it with detailed requirements, specifications, and technical considerations.",
      "mcp_tools": []
    },
    {
      "name": "implementer",
      "system_prompt": "You are a developer. Take the enriched project specification and create the implementation using the available tools.",
      "mcp_tools": ["create_file", "read_file", "create_directory"]
    },
    {
      "name": "documenter",
      "system_prompt": "You are a technical writer. Create comprehensive documentation including README and usage examples.",
      "mcp_tools": ["create_file", "read_file"]
    },
    {
      "name": "deployer",
      "system_prompt": "You are a DevOps specialist. Prepare the project for deployment using git.",
      "mcp_tools": ["git_init", "git_add", "git_commit"]
    }
  ],
  "retry_count": 2,
  "on_error": "abort"
}
```

### How It Works

1. User sends a project description
2. **Stage 1 (Enricher)**: Expands the idea into detailed specs
3. **Stage 2 (Implementer)**: Creates the code using file tools
4. **Stage 3 (Documenter)**: Writes documentation
5. **Stage 4 (Deployer)**: Sets up git repository
6. Final result is returned to user

## UI Configuration

### Chat Sidebar

1. Click the gear icon next to the agent selector
2. Go to the **Sub-Agents** tab (for flat) or **Pipeline** tab (for hierarchy)
3. Configure the settings
4. Click **Save** to persist the configuration

### Create Agent Page

1. Navigate to `/agents`
2. Click **Create Agent**
3. Select the supervisor graph type
4. Fill in the configuration
5. Save the new agent

## API Usage

### Flat Supervisor API

```bash
curl -X POST "http://localhost:8123/langgraph-supervisor-agent/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Help me analyze this codebase and write tests",
    "agent_config": {
      "supervisor_prompt": "You are a tech lead...",
      "sub_agents": ["chatbot", "github-mcp-agent"]
    }
  }'
```

### Pipeline Supervisor API

```bash
curl -X POST "http://localhost:8123/langgraph-supervisor-hierarchy-agent/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Create a TODO app with React",
    "agent_config": {
      "pipeline_stages": [
        {
          "name": "design",
          "system_prompt": "Design the app architecture...",
          "mcp_tools": []
        },
        {
          "name": "implement",
          "system_prompt": "Implement the design...",
          "mcp_tools": ["create_file", "create_directory"]
        }
      ]
    }
  }'
```

## Available MCP Tools

The MCP server provides these tools for pipeline stages:

### File Operations
- `read_file` - Read file contents
- `create_file` - Create new files
- `create_directory` - Create directories
- `list_directory` - List directory contents

### Git Operations
- `git_init` - Initialize repository
- `git_add` - Stage files
- `git_commit` - Create commits
- `git_status` - Check status
- `git_log` - View history

### PDF Operations
- `read_pdf` - Read PDF contents
- `search_pdf` - Search in PDFs
- `get_pdf_info` - Get PDF metadata
- `extract_pdf_tables` - Extract tables

## Best Practices

### Flat Supervisor
1. Keep sub-agent count reasonable (3-5 agents)
2. Choose agents with complementary capabilities
3. Write clear supervisor prompts that explain delegation criteria

### Pipeline Supervisor
1. Keep stages focused on single responsibilities
2. Order stages logically (analyze → implement → document → deploy)
3. Only enable tools each stage actually needs
4. Test each stage independently before combining

## Streaming and Visibility

Both supervisors support streaming output. Sub-agent messages are visible in the UI:
- Each sub-agent's work appears as it happens
- The supervisor's synthesis appears at the end
- Tool calls and results are visible for debugging

## Error Handling

### Flat Supervisor
- If a sub-agent fails, the supervisor can retry or delegate to another agent
- The supervisor synthesizes partial results if some agents succeed

### Pipeline Supervisor
- **abort**: Stop the entire pipeline on error
- **skip**: Skip the failed stage and continue with the next
- Configure `retry_count` for automatic retries before failing
