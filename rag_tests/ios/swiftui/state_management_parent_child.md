# @State and @Binding between parent and child views in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 16
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You have a parent SwiftUI view that owns a value-type state (for example, a form model)
and multiple child views that need to both read and mutate parts of that state.
Explain:

- when to use `@State` in the parent and `@Binding` in the children;
- how two-way binding works between parent and child views;
- why value-type models are preferred for this pattern;
- common mistakes (duplicating state, using reference types in `@State`, breaking the single source of truth).

## Expected Concepts

- @State
- @Binding
- value type
- two-way binding
- single source of truth

## RAG Requirement

The answer must reference SwiftUI documentation on state and bindings and clearly
describe the parent/child pattern with value types.

## Notes

Tests understanding of core SwiftUI state-management patterns.

