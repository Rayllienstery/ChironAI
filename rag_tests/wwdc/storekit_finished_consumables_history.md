# StoreKit 2 finished consumables in transaction history

Platform: iOS
Framework: StoreKit
MinOS: iOS 18
Difficulty: intermediate
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

The WWDC StoreKit session \"What’s new in StoreKit and In-App Purchase\" explains a change to **transaction history APIs** for consumables.  
Explain:

- what changed in iOS 18 regarding finished consumable transactions and transaction history;
- how to opt in to this behavior using the `SKIncludeConsumableInAppPurchaseHistory` key in your app’s Info.plist;
- how this affects your need to manually track consumable purchases versus relying on StoreKit’s APIs and App Store Server API;
- any backward-compatibility notes mentioned in the session (e.g. availability on older OS versions when building with Xcode 16).

You do not need to show complete code, but clearly describe the migration path from manually tracking finished consumables to using the updated APIs.

## Expected Concepts

- transaction history APIs
- finished consumables
- SKIncludeConsumableInAppPurchaseHistory
- Info.plist
- App Store Server API
- StoreKit 2

## RAG Requirement

The answer should rely on the WWDC StoreKit session that introduced the new finished-consumables behavior, not just generic StoreKit documentation.

## Notes

This test is intended to pull WWDC24 transcript content about including finished consumables in history.
