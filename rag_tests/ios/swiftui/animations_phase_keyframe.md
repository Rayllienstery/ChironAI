# PhaseAnimator and KeyframeAnimator in SwiftUI

Platform: iOS
Framework: SwiftUI
MinOS: iOS 17
Difficulty: advanced
Concept Mode: all
RAG Strict: true

## Question

You want to build a complex icon animation in SwiftUI that:
- cycles through several discrete phases (idle, hover, pressed);
- uses different animation curves per phase;
- and then runs a keyframe-based bounce when the user taps.

Explain:

- when to use `PhaseAnimator` versus `KeyframeAnimator`;
- how the `phases` parameter and `.animation` closure work in `PhaseAnimator`;
- how to define keyframes that animate a value over time in `KeyframeAnimator`;
- how to structure state so that animation remains predictable and testable.

## Expected Concepts

- PhaseAnimator
- phases
- .animation modifier
- KeyframeAnimator
- keyframes

## RAG Requirement

The answer must reference SwiftUI documentation on controlling animation timing and movements
using phase and keyframe animators.

## Notes

Checks understanding of modern, fine-grained animation APIs in SwiftUI.

