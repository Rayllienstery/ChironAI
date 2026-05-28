# Local Extension Registry Fallback

`extensions.json` is a local/offline fallback registry for development and
bootstrap startup. The canonical public registry is:

https://github.com/Rayllienstery/ChironAI-Extensions-Registry

The fallback may keep local-only fields such as `source_path`, `default_ref`,
and `latest_version` so tests and offline startup can install bundled bootstrap
copies. Those fields must not be treated as the public registry contract.

Target public registry behavior:

- central registry stores discovery metadata and repository identity;
- available versions are fetched from each extension GitHub repository;
- stable installs prefer immutable GitHub release artifacts;
- local `source_path` is reserved for development and offline fallback only.
