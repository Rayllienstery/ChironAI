# Getting Started

Welcome to ChironAI. This guide walks through the first steps after the WebUI starts.

## Start the server

Run `start_webui.bat` (Windows) or your usual launch script. When the CoreUI shell loads, check the **Dashboard** tab for service health and the active port.

## Pick a model

Open **LLM Proxy → Builds**, create or select a build, and choose a provider-backed model. Use **Model Tester** on the same tab to send a quick prompt before wiring RAG.

## Enable RAG (optional)

If Qdrant and a collection are configured, attach a **RAG collection** to the build or set defaults under **RAG Fusion Proxy**. See **RAG Collections** for precedence rules.

## Where to go next

- **LLM Proxy Builds** — route traffic through configured builds
- **RAG** — manage collections and test retrieval
- **Crawler** — ingest documents into Qdrant
- **Settings** — theme, locale, and poll intervals

Use the sidebar **Help** tab anytime, or open a deep link such as `?help=builds`.
