import { describe, expect, it } from "vitest";
import {
  DEVELOPER_TOOL_TAB_IDS,
  filterSidebarTabs,
  normalizeActiveTab,
  parseDeveloperMode,
} from "./developerMode";

const SAMPLE_TABS = [
  { id: "dashboard", section: "Main" },
  { id: "llm-proxy", section: "Core Functionality" },
  { id: "testing", section: "Developer Tools" },
  { id: "swagger", section: "Developer Tools" },
];

describe("parseDeveloperMode", () => {
  it("defaults to false when unset", () => {
    expect(parseDeveloperMode(undefined)).toBe(false);
    expect(parseDeveloperMode(null)).toBe(false);
    expect(parseDeveloperMode("")).toBe(false);
  });

  it("parses explicit true values", () => {
    expect(parseDeveloperMode(true)).toBe(true);
    expect(parseDeveloperMode("true")).toBe(true);
    expect(parseDeveloperMode("TRUE")).toBe(true);
  });
});

describe("filterSidebarTabs", () => {
  it("hides Developer Tools when developer mode is off", () => {
    const tabs = filterSidebarTabs(SAMPLE_TABS, false);
    expect(tabs.map((tab) => tab.id)).toEqual(["dashboard", "llm-proxy"]);
  });

  it("keeps production tabs available when developer mode is off", () => {
    const tabs = filterSidebarTabs(SAMPLE_TABS, false);
    expect(tabs.some((tab) => tab.id === "dashboard")).toBe(true);
    expect(tabs.some((tab) => tab.id === "llm-proxy")).toBe(true);
  });

  it("shows Developer Tools when developer mode is on", () => {
    const tabs = filterSidebarTabs(SAMPLE_TABS, true);
    expect(tabs.map((tab) => tab.id)).toEqual([
      "dashboard",
      "llm-proxy",
      "testing",
      "swagger",
    ]);
  });
});

describe("normalizeActiveTab", () => {
  it("redirects hidden developer tabs to dashboard", () => {
    for (const tabId of DEVELOPER_TOOL_TAB_IDS) {
      expect(normalizeActiveTab(tabId, false)).toBe("dashboard");
    }
  });

  it("preserves production tabs when developer mode is off", () => {
    expect(normalizeActiveTab("llm-proxy", false)).toBe("llm-proxy");
    expect(normalizeActiveTab("help", false)).toBe("help");
  });
});
