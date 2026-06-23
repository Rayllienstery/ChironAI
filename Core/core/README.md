# Core

Shared infrastructure and contracts used by modules. No business logic.  
Named **core** (not "platform") to avoid shadowing Python's standard library `platform` module.

| Package | Purpose |
|---------|---------|
| [config](config/) | Typed configuration models and YAML/env loading |
| [shared](shared/) | Common types, errors, and utilities used by multiple modules |
| [contracts](contracts/) | Inter-module API contracts (HTTP/JSON, DTOs, OpenAPI) |

Modules depend only on **core** (and on each other's **contracts**, not implementations).
