# Indexing Content

RAG is only as good as the chunks in Qdrant. The **Crawler / Indexer** tab and host ingestion pipelines turn source documents into embedded points with metadata. This guide covers the operational path from raw docs to a build-ready collection.

## End-to-end pipeline

```
Sources (git, HTTP, files) → Crawler / pipeline → Chunk + embed → Upsert Qdrant
     → Verify in RAG tab → Attach collection to build → Test via Model Tester
```

Plan for iteration: first index a **small** representative sample, validate retrieval, then scale up.

## Sources you can ingest

Deployment-specific, but commonly:

- Local markdown / code trees (project docs, ADRs)
- Git repositories (branch-filtered)
- Crawled HTTP sites (respect robots and rate limits)
- Preprocessed exports from CI

The **Crawler** tab exposes configured pipelines, job status, and errors. Failed jobs should surface in UI and **Logs** — do not assume silence means success.

## Typical operator workflow

1. **Prepare sources** — ensure paths or URLs are readable by the WebUI host process (permissions, VPN, mounts).
2. **Choose target collection** — name reflects domain (`ios-18-docs`, `team-handbook`). Prefer new collection over overwriting while experimenting.
3. **Run indexer** — start job from **Crawler**; watch progress and error panel.
4. **Validate in RAG tab** — collection appears with non-zero points; run retrieval test with known phrases.
5. **Wire to proxy** — set collection on build or global Model settings.
6. **Regression** — add cases to **RAG Tests** (Testing tab) if your team uses them.

## Chunking and metadata

Ingestion splits documents into chunks. Quality drivers:

| Knob | Effect |
|------|--------|
| Chunk size | Larger = more context per hit, less precise matching |
| Overlap | Reduces boundary cuts through sentences |
| Metadata | `symbol`, `framework`, `source`, `section` power filtered retrieval |

When chunks lack metadata, intent filters (symbol/framework) cannot narrow results — retrieval still works but may feel “fuzzy”.

Inspect sample payloads in Qdrant dashboard or RAG test output before full reindex.

## Embedding model consistency

All points in a collection must use the **same embedding model** configuration as queries at retrieval time. If you change embed models in **RAG Fusion Proxy → Model settings**:

1. Plan downtime or new collection name
2. Re-index entire corpus
3. Update builds to point at new collection
4. Retire old collection after verification

Mixing old and new vectors in one collection produces nonsense similarity scores.

## Re-indexing and updates

| Event | Action |
|-------|--------|
| Doc content changed | Incremental or full reindex (pipeline-dependent) |
| New major OS/SDK release | New collection or version suffix (`docs-ios-19`) |
| Bad retrieval after config tweak | Re-run retrieval tests; consider re-chunk |
| Qdrant reset / new volume | Full reindex mandatory |

Keep a runbook note: last successful index time, source commit hash, collection name, embed model id.

## Crawler tab tips

- Start with `--dry-run` or small path glob if your pipeline supports it
- Watch disk: Qdrant storage grows with chunk count and vector dimension
- Parallel jobs may contend for GPU/CPU used by embedding — stagger heavy jobs
- Network crawls: configure timeouts; hung jobs block operator visibility

## Permissions and paths

Common failures:

- WebUI service account cannot read UNC/share paths
- Docker crawler container lacks volume mount for host docs
- Git credentials missing for private repos
- SSL errors on internal HTTPS doc servers

Fix permissions at the OS/container level — the UI only reports the failure.

## Quality checklist before production

- [ ] Retrieval test returns expected doc titles for 5+ known queries
- [ ] Model Tester shows relevant context snippets (not empty / unrelated)
- [ ] Collection point count stable after job completes
- [ ] Builds reference correct collection name
- [ ] RAG Tests pass (if used in CI)
- [ ] Disk backup strategy for Qdrant volume documented

## Related topics

- **RAG Collections** — precedence and tuning
- **LLM Proxy Builds** — attach indexed collection
- **Troubleshooting** — empty retrieval, Qdrant connection
- **Logs & Debugging** — ingestion error logs
