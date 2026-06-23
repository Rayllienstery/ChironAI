# SwiftUI SubscriptionStoreView option groups and group sets

Platform: iOS
Framework: SwiftUI
MinOS: iOS 18
Difficulty: advanced
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

In the WWDC24 SubscriptionStoreView session Apple demonstrates **subscription option groups** and **group sets** (for example grouping by premium/basic levels of service).  
Explain:

- what a subscription option group is and how it is declared inside `SubscriptionStoreView`;
- how group sets (`SubscriptionOptionGroupSet` or similar APIs) help you avoid boilerplate when you have multiple groups;
- how to attach **group-specific marketing content** that changes when the active group/tab changes;
- how groups interact with control styles and placements.

Provide a short code example that:

1. Declares a `SubscriptionStoreView` for a group ID.  
2. Creates two option groups (e.g. **Premium** and **Basic**) using a group set or equivalent API.  
3. Provides different marketing content for each group.

## Expected Concepts

- SubscriptionStoreView
- subscription option group
- group set
- marketing content
- premium plan
- basic plan

## RAG Requirement

The answer should be grounded in the WWDC24 example with a streaming app that uses subscription option groups and marketing content.

## Notes

This test is meant to select WWDC24 transcript content describing option groups, group sets and marketing content in SubscriptionStoreView.*** End Patch``` */}
