# RAG system prompts

Each `.md` file in this directory is a **prompt name** (filename without extension). The content is the system prompt prefix used for RAG (the suffix `=================================` is appended automatically).

## Switching prompts

- **Config:** In `config/rag.yaml` set `rag.prompt` to the desired name (e.g. `system_rag_v1`).
- **Environment:** Override with `RAG_PROMPT=other_prompt` (name = stem of `other_prompt.md`).

## Adding a new prompt

1. Add a new file, e.g. `prompts/my_prompt.md`, with your system prompt text.
2. Use it by setting `rag.prompt: "my_prompt"` in `config/rag.yaml` or `RAG_PROMPT=my_prompt`.

## Listing available prompts

From Python:

```python
from config.rag_prompts import list_rag_prompt_names
print(list_rag_prompt_names())  # e.g. ['system_rag_v1', 'concise']
```
