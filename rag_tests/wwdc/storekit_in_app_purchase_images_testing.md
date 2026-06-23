# StoreKit Testing: in-app purchase images in configuration files

Platform: iOS
Framework: StoreKit
MinOS: iOS 18
Difficulty: beginner
Rag Required: no
Concept Mode: all
RAG Strict: true

## Question

According to the WWDC StoreKit testing session, Xcode 16 lets you attach **test images** to products in a StoreKit configuration file.  
Explain:

- where in the StoreKit configuration editor you add an image for a product;
- how that image is used when testing `ProductView` or `StoreView` in your app (for example, with `prefersPromotionalIcon` enabled);
- why these images are only for local testing and how they relate to real App Store metadata;
- how this feature can help you iterate on in-app purchase UI without publishing changes to App Store Connect.

## Expected Concepts

- StoreKit configuration file
- in-app purchase image
- ProductView
- StoreView
- prefersPromotionalIcon
- local testing

## RAG Requirement

The answer should reference behavior and guidance from the WWDC StoreKit testing session, not just API references.

## Notes

This test should make the RAG pipeline retrieve WWDC content describing test images in StoreKit configuration.*** End Patch
