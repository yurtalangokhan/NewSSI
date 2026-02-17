FROM python:3.11-slim

WORKDIR /app

# Install git, Docker CLI, Node.js, JDK and other required tools
RUN apt-get update && apt-get install -y \
    git \
    curl \
    gnupg \
    unzip \
    default-jdk \
    && curl -fsSL https://get.docker.com | sh \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml .
COPY server.py .
COPY src/ src/

# Install Python dependencies using uv
RUN uv pip install --system \
    fastmcp httpx asyncpg pymupdf ddgs \
    pytest flake8 pylint

# Create workspace directory with proper permissions
RUN mkdir -p /workspace && chmod 777 /workspace

# Expose port
EXPOSE 8001

# Environment variables
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8001
ENV WORKSPACE_DIR=/workspace
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Run the server
CMD ["python", "server.py"]
