# Single container: builds the React app, then serves it and the API from FastAPI.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY sample_uploads/ ./sample_uploads/
COPY --from=web /web/dist ./frontend/dist
ENV DATABASE_PATH=/tmp/continuityos.db FRONTEND_DIST=/app/frontend/dist RESEED_ON_START=1
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
