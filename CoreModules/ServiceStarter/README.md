# ServiceStarter

Core module that **starts**, **installs** (Windows), and reports **status** for:

- **Docker Desktop** (Windows download + silent install; engine readiness)
- **Ollama** (installer + `ollama serve` on configurable port, default `11343`)
- **Qdrant** (Docker image pull + container `qdrant` on port `6333`)

## Install

```bash
pip install -e CoreModules/ServiceStarter
```

## Python API

```python
from servicestarter import ServiceStarter

ss = ServiceStarter()
print(ss.status())
ss.ensure_docker_running()
ss.start_qdrant()
```

## CLI

```bash
python -m servicestarter status
python -m servicestarter start-all --services qdrant
python -m servicestarter start-all --services docker,qdrant,ollama
```

See `servicestarter.config` for environment variables.

After installing Ollama on Windows, restart the terminal (or sign out) if `ollama` is not yet on `PATH`.

ChironAI `config/models.yaml` still defaults Ollama HTTP to port `11434`. Set `OLLAMA_EMBED_URL`, `OLLAMA_CHAT_URL`, etc., or `OLLAMA_BASE_URL` / `OLLAMA_PORT` so the app matches the ServiceStarter Ollama port (default `11343`).
