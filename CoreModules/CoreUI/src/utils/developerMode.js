export const DEVELOPER_TOOL_TAB_IDS = [
  "testing",
  "coreui-showcase",
  "dev-documentation",
  "swagger",
  "performance",
];

export function parseDeveloperMode(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") return value.toLowerCase() === "true";
  return false;
}

export function filterSidebarTabs(allTabs, developerMode) {
  if (developerMode) return allTabs;
  return allTabs.filter((tab) => tab.section !== "Developer Tools");
}

export function normalizeActiveTab(activeTab, developerMode) {
  if (developerMode) return activeTab;
  if (DEVELOPER_TOOL_TAB_IDS.includes(activeTab)) return "dashboard";
  return activeTab;
}

export function removePrebootLoader() {
  if (typeof document === "undefined") return;
  const loader = document.getElementById("app-loader");
  if (!loader) return;

  loader.classList.add("standby-screen--fade-out");
  const remove = () => loader.remove();
  loader.addEventListener("transitionend", remove, { once: true });
  window.setTimeout(remove, 220);
}
