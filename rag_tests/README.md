# RAG Tests

Markdown-defined tests for RAG proxy behaviour. Each test specifies a question, expected concepts, and optional RAG requirements. Tests are run against the configured Ollama model and RAG retrieval; results are validated for concept coverage and RAG usage.

## Template (full example)

Create a `.md` file under `rag_tests/` (e.g. in a folder like `ios/swiftui/`) with the following structure:

```markdown
# Test name (short title)

Platform: iOS
Framework: SwiftUI
MinOS: iOS 18
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

Your question to the model (e.g. "What is the @Observation macro and how do you use it with SwiftUI?").

## Expected Concepts

- concept one
- concept two

## RAG Requirement

The answer must reference retrieved documentation or RAG context.

## Notes

Optional notes (e.g. what this test verifies).
```

- **RAG Strict** is optional. When `true`, the test passes only if the model’s response overlaps with retrieved chunk text (not just that RAG was used).
- **MinOS** and **Notes** are optional.

## Field reference

| Field | Description |
|-------|-------------|
| **Platform** | e.g. iOS, macOS, watchOS, visionOS. Used for filtering. |
| **Framework** | e.g. SwiftUI, UIKit. Used for filtering. |
| **Difficulty** | beginner, intermediate, advanced. Used for filtering. |
| **Concept Mode** | `any` = at least one expected concept must appear; `all` = every expected concept must appear. Default: `all`. |
| **RAG Strict** | Optional. `true` / `yes` / `1` = require response text to overlap retrieved chunks. Default: false. |
| **MinOS** | Optional minimum OS (e.g. iOS 18). |
| **Notes** | Optional free text. |

## Folder structure

Tests are organized under `rag_tests/` by platform and framework, for example:

- `rag_tests/ios/swiftui/` – iOS SwiftUI tests  
- `rag_tests/ios/uikit/` – iOS UIKit tests  
- `rag_tests/concurrency/` – Concurrency tests  

Filters in the WebUI and CLI are derived from the **Platform**, **Framework**, and **Difficulty** metadata in these files.

## How to add tests

1. **Manually:** Create a new `.md` file under `rag_tests/` (e.g. `ios/swiftui/my_test.md`) using the template above.
2. **WebUI:** Open the RAG Tests tab, click **Create test**, fill in the form (including optional RAG Strict), and save.

Ensure each test has a **Question** and at least one **Expected Concepts** entry if you want concept validation.

## How to run tests

- **WebUI:** Open the RAG Tests tab, select a model, then use **Run all**, **Run filtered**, or **Run selected**. You can also click **Run** on a single row to run that test only.
- **CLI (e.g. for CI):**  
  `python -m api.cli rag-tests run --model <model_name>`  
  Optional: `--filter-platform`, `--filter-framework`, `--filter-difficulty`, or `--test-id <id>` (repeatable for specific tests).  
  Exit code is 0 if all tests pass, 1 otherwise.

Example:

```bash
python -m api.cli rag-tests run --model llama3.2
python -m api.cli rag-tests run --model llama3.2 --filter-platform iOS --filter-framework SwiftUI
python -m api.cli rag-tests run --model llama3.2 --test-id ios_swiftui_observation_macro
```
