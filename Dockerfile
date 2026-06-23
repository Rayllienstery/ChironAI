# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim AS coreui-build
WORKDIR /build
COPY CoreModules/CoreUI/package.json CoreModules/CoreUI/package-lock.json ./CoreModules/CoreUI/
RUN cd CoreModules/CoreUI && npm ci
COPY CoreModules/CoreUI/ ./CoreModules/CoreUI/
COPY CoreModules/Localization ./CoreModules/Localization
WORKDIR /build/CoreModules/CoreUI
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
COPY Core ./Core
COPY CoreModules/Security ./CoreModules/Security
COPY CoreModules/ExtensionsSandbox ./CoreModules/ExtensionsSandbox
COPY CoreModules/RagService ./CoreModules/RagService
COPY CoreModules/LlmProxy ./CoreModules/LlmProxy
COPY CoreModules/LlmInteractor ./CoreModules/LlmInteractor
COPY CoreModules/ErrorManager ./CoreModules/ErrorManager
COPY --from=coreui-build /build/CoreModules/CoreUI/dist ./CoreModules/CoreUI/dist

RUN pip install --upgrade pip \
    && pip install . \
    && pip install ./Core/modules/html_md \
    && pip install ./Core/modules/webui_backend \
    && pip install ./Core/modules/crawler_service \
    && pip install ./Core/modules/extensions_backend \
    && pip install ./CoreModules/Security \
    && pip install ./CoreModules/ExtensionsSandbox \
    && pip install ./CoreModules/RagService \
    && pip install ./CoreModules/LlmProxy \
    && pip install ./CoreModules/LlmInteractor \
    && pip install ./CoreModules/ErrorManager

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${WEBUI_PORT:-5000}/health || exit 1

CMD ["python", "-m", "webui_backend.app", "start"]
