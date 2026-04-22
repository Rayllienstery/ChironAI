# StoreKit Testing in Xcode 16: App Policies and dialogs

Platform: iOS
Framework: StoreKit
MinOS: iOS 18
Difficulty: intermediate
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

In the WWDC24 StoreKit testing session Apple introduced new capabilities in **StoreKit configuration files** in Xcode 16.  
Explain:

- how to use the new App Policies section in a StoreKit configuration file to test your app’s license agreement and privacy policy locally;
- how these values show up inside `SubscriptionStoreView` (for example, when tapping the terms of service and privacy policy buttons);
- how to configure and test billing issue messages and the billing retry flow using StoreKit Testing and the transaction manager;
- how disabling system dialogs in the configuration affects automated UI tests and default flows.

Provide a narrative explanation of how you would set up a StoreKit configuration to exercise these scenarios in Xcode without touching App Store Connect.

## Expected Concepts

- StoreKit Testing in Xcode
- StoreKit configuration file
- App Policies
- billing retry
- transaction manager
- system dialogs

## RAG Requirement

The answer should be grounded in the specific WWDC24 StoreKit testing session, including the transaction manager and App Policies editor.

## Notes

This test targets WWDC content on StoreKit Testing in Xcode 16, not generic StoreKit docs.*** End Patch
