# Imagem única do BC Pedidos: API (padrão) e relay (`python -m pedidos.relay`).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CONTRACTS_DIR=/app/contracts/schemas

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Contratos (JSON Schema) validados antes de gravar na outbox.
COPY contracts ./contracts

RUN useradd --uid 10001 --no-create-home app
USER 10001

EXPOSE 8000
CMD ["uvicorn", "pedidos.api:app", "--host", "0.0.0.0", "--port", "8000"]
