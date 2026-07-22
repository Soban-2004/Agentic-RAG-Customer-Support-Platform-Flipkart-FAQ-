# --- Stage 1: build the React frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime, serving the API + the built frontend ---
FROM python:3.10-slim
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# Single worker only -- the shared FunctionAgent/Settings and the SQLite-backed
# session memory (src/memory/persistent_memory.py) both assume one process.
# See README's run-instructions notes.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
