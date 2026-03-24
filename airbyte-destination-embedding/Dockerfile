FROM python:3.11-slim

WORKDIR /destination

COPY pyproject.toml .
COPY destination_embedding/ destination_embedding/

RUN pip install --no-cache-dir -e .

# Airbyte protocol: entrypoint receives command as first arg
ENTRYPOINT ["python", "-m", "destination_embedding"]
