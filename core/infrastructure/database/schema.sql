-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Logs table
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL,
    source TEXT,
    message TEXT NOT NULL,
    error_type TEXT,
    metadata TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Model tester settings
CREATE TABLE IF NOT EXISTS model_tester_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    model TEXT,
    prompt_name TEXT,
    swift_mode TEXT,
    temperature REAL,
    top_p REAL,
    reasoning_level TEXT,
    use_rag INTEGER DEFAULT 1,
    top_k INTEGER,
    rag_config TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- App settings
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- RAG test runs history
CREATE TABLE IF NOT EXISTS rag_test_runs (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    results TEXT
);

-- RAG collection metadata (framework_id, version, last_refreshed for TTL)
CREATE TABLE IF NOT EXISTS rag_collection_meta (
    collection_name TEXT PRIMARY KEY,
    framework_id TEXT NOT NULL,
    version TEXT,
    last_refreshed_at TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_collection_meta_framework_id ON rag_collection_meta(framework_id);

-- Gemini tool-call state cache (internal resilience for thought_signature/name recovery)
CREATE TABLE IF NOT EXISTS gemini_tool_call_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    model TEXT NOT NULL,
    function_name TEXT,
    thought_signature TEXT,
    trace_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(call_id, model)
);

CREATE INDEX IF NOT EXISTS idx_gemini_tool_call_state_call_id ON gemini_tool_call_state(call_id);
CREATE INDEX IF NOT EXISTS idx_gemini_tool_call_state_updated_at ON gemini_tool_call_state(updated_at);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_logs_session_id ON logs(session_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
CREATE INDEX IF NOT EXISTS idx_tester_settings_session_id ON model_tester_settings(session_id);
CREATE INDEX IF NOT EXISTS idx_rag_test_runs_created_at ON rag_test_runs(created_at);

-- CoreUI notification center (errors + history events; not mixed with logs)
CREATE TABLE IF NOT EXISTS coreui_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    metadata TEXT,
    aggregation_key TEXT,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_occurrence_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_console_error INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dismissed_at TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_coreui_notifications_session ON coreui_notifications(session_id);
CREATE INDEX IF NOT EXISTS idx_coreui_notifications_created ON coreui_notifications(created_at);
