# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim AS coreui-build
WORKDIR /build/CoreModules/CoreUI
COPY CoreModules/CoreUI/package.json CoreModules/CoreUI/package-lock.json ./
RUN npm ci
COPY CoreModules/CoreUI/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY application api config core domain infrastructure chironai_security extensions_sandbox extensions_backend webui_backend modules ./ 
COPY --from=coreui-build /build/CoreModules/CoreUI/dist ./CoreModules/CoreUI/dist

RUN pip install --upgrade pip \
    && pip install -e . \
    && pip install -e modules/webui_backend \
    && pip install -e modules/crawler_service \
    && pip install -e CoreModules/RagService \
    && pip install -e CoreModules/LlmProxy \
    && pip install -e CoreModules/LlmInteractor \
    && pip install -e CoreModules/ErrorManager

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${WEBUI_PORT:-5000}/health || exit 1

CMD ["python", "-m", "webui_backend.app", "start"]
