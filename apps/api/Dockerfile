FROM python:3.12-slim
WORKDIR /app
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/api/src ./apps/api/src
COPY data ./data
COPY evals ./evals
RUN pip install --no-cache-dir "./apps/api[postgres]"
ENV PYTHONUNBUFFERED=1
WORKDIR /app/apps/api
EXPOSE 8000
CMD ["sh", "-c", "python -m nova_api.seed && uvicorn nova_api.main:app --host 0.0.0.0 --port 8000"]
