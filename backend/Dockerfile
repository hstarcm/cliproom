FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[telemetry]"

EXPOSE 8000
# --no-access-log: access lines would contain room IDs (SR-4)
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
