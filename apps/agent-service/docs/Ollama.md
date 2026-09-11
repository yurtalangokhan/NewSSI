# Using Ollama

⚠️ _**Note:** Ollama support in agent-service-toolkit is experimental and may not work as expected. The instructions below have been tested using Docker Desktop on a MacBook Pro. Please file an issue for any challenges you encounter._

You can also use [Ollama](https://ollama.com) to run the LLM powering the agent service.

1. Install Ollama using instructions from https://github.com/ollama/ollama
1. Install any model you want to use, e.g. `ollama pull llama3.2` and set the `OLLAMA_MODEL` environment variable to the model you want to use, e.g. `OLLAMA_MODEL=llama3.2`

If you are running the service locally (e.g. `python src/run_service.py`), you should be all set!

## Multi-step connector agents

A model advertising tool support may still fail after the first tool response.
Check the deployed template with Ollama's `/api/show`: tool definitions must remain
in context when the latest message is a tool result, not only a user message.
The observed `llama3.1:8b` template omitted definitions at that stage and treated
a resource listing as the final answer. Direct replay reproduced this behavior.

PG Connector Agent uses the installed `qwen3.5:9b` model, verified with native
resource discovery and a live PostgreSQL read. Validate both the executed calls
and the final answer with real rows when changing the model or its template;
scripted-model unit tests alone do not verify provider behavior.

If you are running the service in Docker, you will also need to:

1. [Configure the Ollama server as described here](https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server), e.g. by running `launchctl setenv OLLAMA_HOST "0.0.0.0"` on MacOS and restart Ollama.
1. Set the `OLLAMA_BASE_URL` environment variable to the base URL of the Ollama server, e.g. `OLLAMA_BASE_URL=http://host.docker.internal:11434`
1. Alternatively, you can run `ollama/ollama` image in Docker and use a similar configuration (however it may be slower in some cases).
