# Build the browser app independently of the runtime image.
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=$VITE_BASE_PATH
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt
COPY src/ ./src/
COPY config/ ./config/
COPY db/ ./db/
COPY data/dataset/ ./data/dataset/
COPY main.py ./
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health/ready',timeout=3)"
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --ws-max-size ${MAX_FRAME_BYTES:-6000000} --ws-max-queue 4 --forwarded-allow-ips ${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
