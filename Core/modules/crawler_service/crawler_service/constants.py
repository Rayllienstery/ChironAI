"""Default crawler path allowlists and Swift Book slug filters."""

from __future__ import annotations

DEFAULT_FRAMEWORK_ROOT_PREFIXES: list[str] = [
    "/documentation/swift",
    "/documentation/swift/concurrency",
    "/documentation/swiftui",
    "/documentation/uikit",
    "/documentation/appkit",
    "/documentation/foundation",
    "/documentation/combine",
    "/documentation/tvuikit",
    "/documentation/watchkit",
    "/documentation/webkit",
    "/documentation/widgetkit",
    "/documentation/uniformtypeidentifiers",
    "/documentation/usernotifications",
    "/documentation/usernotificationsui",
    "/documentation/vision",
    "/documentation/visionkit",
    "/documentation/weatherkit",
    "/documentation/weatherkitrestapi",
    "/documentation/passkit",
    "/documentation/walletorders",
    "/documentation/workoutkit",
    "/documentation/coredata",
    "/documentation/cloudkit",
    "/documentation/xctest",
    "/documentation/xcuiautomation",
    "/documentation/xcode",
    "/documentation/xcodecloud",
    "/documentation/xcodekit",
    "/documentation/xcselect",
    "/documentation/watchconnectivity",
    "/documentation/xpc",
    "/documentation/videotoolbox",
    "/documentation/virtualization",
    "/documentation/wifiaware",
    "/documentation/wi_fi_infrastructure",
    "/documentation/visionos",
    "/documentation/visualintelligence",
    "/documentation/webkitjs",
    "/documentation/backgroundtasks",
    "/documentation/network",
]

DEFAULT_EXCLUDED_PATH_SUBSTRINGS: list[str] = [
    "/release-notes",
    "/wwdc",
    "/topics/",
    "/collections/",
]

SWIFT_BOOK_ALLOWED_SLUGS: set[str] = {
    "thebasics",
    "basicoperators",
    "stringsandcharacters",
    "collectiontypes",
    "controlflow",
    "functions",
    "closures",
    "enumerations",
    "structuresandclasses",
    "properties",
    "methods",
    "subscripts",
    "inheritance",
    "initialization",
    "deinitialization",
    "optionalchaining",
    "errorhandling",
    "concurrency",
    "macros",
    "typecasting",
    "nestedtypes",
    "extensions",
    "protocols",
    "generics",
    "opaquetypes",
    "automaticreferencecounting",
    "memorysafety",
    "accesscontrol",
    "advancedoperators",
    "lexicalstructure",
    "types",
    "expressions",
    "statements",
    "declarations",
    "attributes",
    "patterns",
    "genericparametersandarguments",
    "summaryofthegrammar",
}

SWIFT_BOOK_EXCLUDED_SLUGS: set[str] = {
    "aboutswift",
    "compatibility",
    "guidedtour",
    "aboutthelanguagereference",
    "revisionhistory",
}

CRAWL_CONCURRENCY = 6
CRAWL_GOTO_TIMEOUT_MS = 30000
CRAWL_DOM_READY_WAIT_MS = 2500
CRAWL_MAX_RETRIES_429 = 3
CRAWL_BACKOFF_BASE_SEC = 2
CRAWL_BACKOFF_MAX_SEC = 60
