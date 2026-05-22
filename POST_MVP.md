# Post MVP

Backlog after the Minimum Viable Product: RAG quality, answer validation, prompt experiments, and external evaluation. Original location in the task list: [TODO.md](TODO.md) (section "Post MVP").

- [ ] **Local RAG quality metrics** — implement Hit@K / MRR / "correct chunk in top-N" measurements based on a reference set of queries; calculate distribution by models and configs, save results to a file/DB for comparison between versions.
- [ ] **Automatic answer checks** — add checks for forbidden patterns (force unwrap, hallucinated APIs, Russian comments in code, missing links to RAG chunks when present), fail tests or mark the query as "failed".
- [ ] **A/B testing of prompts** — ability to run the same set of queries through different system prompt variants (Swift 5 / Swift 6 / short / strict) and compare quality metrics and error counts.
- [ ] **Semi-manual expert evaluation** — a small but carefully labeled set of complex queries (Observation, Liquid Glass, complex RAG cases), where an expert manually marks the correctness of facts, architectural recommendations, and adherence to self-check principles.
- [ ] **AI analysis of test queries** — integration with an external AI API for analyzing test queries: a button in the WebUI sends all information about a test query (user question, found RAG chunks, model answer, metrics) to an external AI, which comments on answer quality, relevance of found chunks, adherence to principles, and suggests improvements. API key configuration via env, optional feature enablement.
