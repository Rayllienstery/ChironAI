# List, ForEach and identity in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 15
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You display a dynamic list of items in SwiftUI and support insert/delete/move operations.
Explain:

- how `List` and `ForEach` use identity to diff changes;
- when to conform your model to `Identifiable` versus specifying an explicit `id:` key path;
- what can go wrong if you use an unstable or non-unique identifier (e.g. `id: \\.self` for mutable models);
- best practices for stable identity in lists backed by network or database models.

## Expected Concepts

- List
- ForEach
- Identifiable
- id:
- diffing
- stable identity

## RAG Requirement

The answer must use SwiftUI documentation for lists and identity and clearly
explain why stable, unique IDs are required for correct diffing.

## Notes

Validates understanding of identity and diffing in SwiftUI collections.

