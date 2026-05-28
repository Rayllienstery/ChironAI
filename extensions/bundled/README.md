# Bundled Extension Bootstrap Copies

These directories are trusted bootstrap copies of the public ChironAI extension
repositories. They are kept in the main repository only so ChironAI can start in
offline/local development mode and auto-install a minimal trusted baseline.

Canonical source repositories:

- `ollama-provider`: https://github.com/Rayllienstery/chironai-extension-ollama-provider
- `open-webui`: https://github.com/Rayllienstery/chironai-extension-open-webui
- `codex-launcher`: https://github.com/Rayllienstery/chironai-extension-codex-launcher

Policy:

- Do not treat `extensions/bundled/*` as the long-term source of truth.
- Make extension feature changes in the extension repository first.
- Sync only runtime payload files back here: `chironai-extension.json`,
  `backend/`, and `icons/`.
- Do not copy repository-only files such as `.git`, `.github`, release scripts,
  validation scripts, dependency inventories, or standalone README files into
  bundled payload directories.
- Keep the bundled manifest version aligned with the latest trusted release used
  by the local fallback registry.

Sync check:

```powershell
python scripts\sync_bundled_extensions.py --check --source-root tmp
```

Sync from local clones:

```powershell
python scripts\sync_bundled_extensions.py --sync --source-root tmp
```

The expected local clone names are:

- `tmp/chironai-extension-ollama-provider`
- `tmp/chironai-extension-open-webui`
- `tmp/chironai-extension-codex-launcher`
