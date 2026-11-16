FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd --create-home borges && chown -R borges /app
USER borges
EXPOSE 8000
# Migra, garante administrador + cliente demonstrativo (idempotente) e sobe a API.
CMD ["sh", "-c", "python -m app.cli init-db && python -m app.cli seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
