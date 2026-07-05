# Extensions

Extensions add providers, UI tabs, and optional Docker-backed services.

## Installing

Place bundled extensions under the configured extensions directory or install via your deployment process. The **Extensions** tab lists discovered manifests, versions, and enable/disable toggles.

## Runtime

Some extensions start companion containers. Use **Extension Runtime** (developer mode) to inspect logs and health. Failed starts usually appear in **Logs** with the extension id in the message.

## UI integration

Enabled extensions may register sidebar tabs or settings panels. Reload the WebUI after enabling a new extension so CoreUI picks up manifest changes.

## Upgrades

When upgrading ChironAI, review extension compatibility in each manifest’s `min_host_version` field before enabling production traffic.
