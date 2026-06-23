# Retain cycles with UIViewController and closures

Platform: iOS
Framework: UIKit
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You have a `UIViewController` that stores closures for timers, animations and network callbacks.
Explain:

- how strong reference cycles arise between view controllers and closures;
- when and why to use `[weak self]` or `[unowned self]` in closures;
- how to avoid retain cycles with `Timer`, `UIViewPropertyAnimator`, and URLSession callbacks;
- trade-offs between weak and unowned references.

## Expected Concepts

- retain cycle
- strong reference
- weak self
- unowned
- closure capture list
- Timer
- deinit

## RAG Requirement

The answer should align with ARC and memory management documentation for Swift / UIKit.

## Notes

Checks deeper understanding of ARC and closure capture semantics in a UIKit context.

