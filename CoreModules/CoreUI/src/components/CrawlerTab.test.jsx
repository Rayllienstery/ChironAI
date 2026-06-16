import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import CrawlerTab from "./CrawlerTab.jsx";

const mockGetCrawlerSources = vi.fn();
const mockGetRagCollections = vi.fn();
const mockGetMdPipelines = vi.fn();
const mockGetIndexerTesterSources = vi.fn();

vi.mock("../services/api.js", () => ({
  getCrawlerSources: (...args) => mockGetCrawlerSources(...args),
  getRagCollections: (...args) => mockGetRagCollections(...args),
  getCrawlerSourcePages: vi.fn().mockResolvedValue({ pages: [] }),
  getProviderCatalog: vi.fn().mockResolvedValue({ providers: [], models: [] }),
  getRagModelSettings: vi.fn().mockResolvedValue({}),
  createCollection: vi.fn(),
  getCreateCollectionStatus: vi.fn(),
  cancelCreateCollection: vi.fn(),
  crawlSource: vi.fn(),
  getCrawlStatus: vi.fn(),
  addCrawlerSource: vi.fn(),
  getCrawlerSource: vi.fn(),
  updateCrawlerSource: vi.fn(),
  getIndexerTesterSources: (...args) => mockGetIndexerTesterSources(...args),
  getIndexerTesterFiles: vi.fn().mockResolvedValue({ files: [] }),
  getMdPipelines: (...args) => mockGetMdPipelines(...args),
  getMdPipeline: vi.fn().mockResolvedValue({ name: "", steps: [] }),
  saveMdPipeline: vi.fn(),
  deleteMdPipeline: vi.fn(),
  previewMdPipeline: vi.fn(),
}));

describe("CrawlerTab smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCrawlerSources.mockResolvedValue({ sources: [] });
    mockGetRagCollections.mockResolvedValue({ collections: [] });
    mockGetMdPipelines.mockResolvedValue({ pipelines: [] });
    mockGetIndexerTesterSources.mockResolvedValue({ sources: [] });
  });

  it("renders Crawler / Indexer heading", async () => {
    render(<CrawlerTab />);
    expect(
      screen.getByRole("heading", { level: 2, name: /Crawler \/ Indexer/i }),
    ).toBeInTheDocument();
  });

  it("shows loading state while sources fetch", async () => {
    mockGetCrawlerSources.mockImplementation(
      () => new Promise(() => {}),
    );
    render(<CrawlerTab />);
    expect(screen.getByText(/Loading sources/i)).toBeInTheDocument();
  });

  it("shows empty state when no sources", async () => {
    render(<CrawlerTab />);
    await waitFor(() => {
      expect(
        screen.getByText(/No crawl sources found/i),
      ).toBeInTheDocument();
    });
  });

  it("shows error when sources fetch fails", async () => {
    mockGetCrawlerSources.mockRejectedValue(new Error("Network down"));
    render(<CrawlerTab />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/something went wrong|network error/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    });
  });

  it("renders sources table when data loads", async () => {
    mockGetCrawlerSources.mockResolvedValue({
      sources: [
        {
          id: "docs",
          url: "https://example.com",
          last_crawled: null,
          total_pages: 3,
          indexed_pages: 1,
        },
      ],
    });
    render(<CrawlerTab />);
    await waitFor(() => {
      expect(screen.getByText("docs")).toBeInTheDocument();
    });
    expect(screen.getByText("https://example.com")).toBeInTheDocument();
  });

  it("switches to MD Pipeline section", async () => {
    render(<CrawlerTab />);
    await waitFor(() => {
      expect(screen.getByText(/No crawl sources found/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("tab", { name: /MD Pipeline/i }));
    expect(screen.getByRole("heading", { level: 3, name: /MD Pipeline/i })).toBeInTheDocument();
  });
});
