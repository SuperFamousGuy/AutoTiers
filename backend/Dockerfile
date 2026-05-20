FROM python:3.12-slim

# System deps for psycopg2-binary and healthchecks (pg_isready)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      postgresql-client \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so they cache when only source changes
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e ".[dev]"

# Copy the rest (alembic, scripts, tests)
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY tests ./tests

RUN chmod +x ./scripts/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
