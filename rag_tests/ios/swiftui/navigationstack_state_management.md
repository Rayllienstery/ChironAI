# NavigationStack and state management in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 16
Difficulty: intermediate
Concept Mode: all
RAG Strict: true

## Question

You build a master–detail flow using `NavigationStack` and `NavigationPath`.
Explain:

- how to model navigation state in a value type (e.g. enum or identifiable models) and bind it to `NavigationPath`;
- how to keep the source of truth for selection in one place (to avoid duplicated state between list and detail);
- how deep linking (restoring a navigation path) should work with `NavigationStack`;
- common mistakes that lead to inconsistent navigation state or broken back navigation.

## Expected Concepts

- NavigationStack
- NavigationPath
- value type state
- source of truth
- deep link
- selection

## RAG Requirement

The answer must rely on SwiftUI documentation about `NavigationStack` / `NavigationPath`
and describe a value-based navigation model.

## Notes

Checks that the model understands modern, state-driven SwiftUI navigation.

