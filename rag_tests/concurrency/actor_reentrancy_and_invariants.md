# Actor reentrancy and invariants in Swift concurrency

Platform: iOS
Framework: Swift
MinOS: iOS 15
Difficulty: advanced
Concept Mode: all
RAG Strict: false

## Question

You design an actor that manages a critical piece of mutable state (for example, a queue of requests).
Explain:

- what actor reentrancy is and when it can occur;
- how to structure actor methods to maintain invariants even under reentrancy;
- when to temporarily allow suspension inside critical sections and when to avoid it;
- common pitfalls (assuming non-reentrancy, leaking partially updated state).

## Expected Concepts

- actor reentrancy
- invariants
- suspension points
- critical section

## RAG Requirement

The answer should align with Swift actor and reentrancy documentation.

## Notes

Tests deep reasoning about correctness properties of actor-based code.

