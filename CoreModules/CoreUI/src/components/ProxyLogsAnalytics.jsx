import React, { useMemo, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts';
import { useThemeChartColors } from '../hooks/useThemeChartColors';
import ProxyLogsPeriodCalendar from './ProxyLogsPeriodCalendar';
import ProxyTraceDetailModal from './ProxyTraceDetailModal';
import '../styles/components/CoreUIPillTabs.css';

const PERIODS = [
  { id: 'day', label: 'Day' },
  { id: 'week', label: 'Week' },
  { id: 'month', label: 'Month' },
  { id: 'year', label: 'Year' },
  { id: 'all', label: 'All time' },
];

const TOP_N = 10;
const MODEL_TOP = 8;

const PIPELINE_OPTIONS = [
  { id: 'mixed', label: 'Mixed' },
  { id: 'rag_fusion', label: 'RAG Fusion' },
];

function pad2(n) {
  return String(n).padStart(2, '0');
}

export function getMetadata(log) {
  if (!log || !log.metadata) return {};
  if (typeof log.metadata === 'string') {
    try {
      return JSON.parse(log.metadata);
    } catch {
      return {};
    }
  }
  return log.metadata;
}

function parseLogDate(log) {
  const ts = log?.timestamp;
  if (!ts) return null;
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? null : d;
}

function isCloudModelName(s) {
  return String(s || '')
    .trim()
    .toLowerCase()
    .endsWith('cloud');
}

function resolveModelLabel(meta) {
  return (meta.model || meta.requested_model || 'N/A').trim() || 'N/A';
}

/**
 * Map a proxy log row to common analytics fields.
 */
function normalizeLogForAnalytics(log) {
  const raw = getMetadata(log);
  const ragContext = raw.rag_context;
  const chunksInfo = Array.isArray(ragContext?.chunks_info) ? ragContext.chunks_info : [];
  const hasRag = (ragContext?.chunks_count > 0) || chunksInfo.length > 0;
  return {
    model: resolveModelLabel(raw),
    ragContext: hasRag ? ragContext : null,
    chunksInfo,
    hasRag,
    latency_ms: raw.latency_ms,
    prompt_tokens: raw.prompt_tokens,
    completion_tokens: raw.completion_tokens,
    total_tokens: raw.total_tokens,
    userPreview: (raw.user_query || '').slice(0, 40),
    proxyBackend: raw.proxy_backend,
  };
}

function bucketKeyForLog(period, selectedDate, d) {
  if (!d || Number.isNaN(d.getTime())) return null;
  const y = d.getFullYear();
  const m = pad2(d.getMonth() + 1);
  const day = pad2(d.getDate());
  const h = d.getHours();
  switch (period) {
    case 'day':
      return `${y}-${m}-${day} ${pad2(h)}:00`;
    case 'week':
    case 'month':
      return `${y}-${m}-${day}`;
    case 'year':
    case 'all':
      return `${y}-${m}`;
    default:
      return `${y}-${m}-${day}`;
  }
}

function enumerateBucketKeys(period, selectedDate) {
  const now = new Date();
  const anchor = selectedDate
    ? new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate())
    : now;
  const keys = [];
  if (period === 'day') {
    const y = anchor.getFullYear();
    const mo = pad2(anchor.getMonth() + 1);
    const da = pad2(anchor.getDate());
    for (let h = 0; h < 24; h += 1) {
      keys.push(`${y}-${mo}-${da} ${pad2(h)}:00`);
    }
  } else if (period === 'week') {
    for (let i = 6; i >= 0; i -= 1) {
      const dt = new Date(now);
      dt.setDate(dt.getDate() - i);
      dt.setHours(0, 0, 0, 0);
      keys.push(`${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}-${pad2(dt.getDate())}`);
    }
  } else if (period === 'month') {
    const y = anchor.getFullYear();
    const mo = anchor.getMonth();
    const dim = new Date(y, mo + 1, 0).getDate();
    for (let day = 1; day <= dim; day += 1) {
      keys.push(`${y}-${pad2(mo + 1)}-${pad2(day)}`);
    }
  } else if (period === 'year') {
    const y = anchor.getFullYear();
    for (let mo = 1; mo <= 12; mo += 1) {
      keys.push(`${y}-${pad2(mo)}`);
    }
  } else if (period === 'all') {
    for (let i = 11; i >= 0; i -= 1) {
      const dt = new Date(now.getFullYear(), now.getMonth() - i, 1);
      keys.push(`${dt.getFullYear()}-${pad2(dt.getMonth() + 1)}`);
    }
  }
  return keys;
}

function shortTickLabel(period, key) {
  if (!key) return '';
  if (period === 'day') {
    const part = key.split(' ')[1] || key;
    return part.replace(':00', 'h');
  }
  if (period === 'week' || period === 'month') {
    const [, mo, da] = key.split('-');
    return `${mo}/${da}`;
  }
  if (period === 'year' || period === 'all') {
    const [yy, mo] = key.split('-');
    return `${yy}-${mo}`;
  }
  return key;
}

function aggregateLogs(logsInput, period, selectedDate, isAutocomplete) {
  const logs = Array.isArray(logsInput) ? logsInput : [];
  const bucketKeys = enumerateBucketKeys(period, selectedDate);
  const bucketOrder = new Map(bucketKeys.map((k, i) => [k, i]));

  const initBuckets = () => {
    const o = {};
    for (const k of bucketKeys) {
      o[k] = {
        withRag: 0,
        withoutRag: 0,
        rag_fusion: 0,
        cloud: 0,
        nonCloud: 0,
      };
    }
    return o;
  };
  const byBucket = initBuckets();

  const byModel = {};
  const byModelRag = {};
  const byRagDocType = {};
  let withRag = 0;
  let withoutRag = 0;
  const withLatency = [];
  const withPromptTokens = [];
  const withCompletionTokens = [];
  const withTotalTokens = [];

  for (const log of logs) {
    const norm = normalizeLogForAnalytics(log);
    const model = norm.model;
    byModel[model] = (byModel[model] || 0) + 1;
    if (!byModelRag[model]) {
      byModelRag[model] = { withRag: 0, withoutRag: 0 };
    }

    if (norm.hasRag) {
      withRag += 1;
      byModelRag[model].withRag += 1;
      for (const chunk of norm.chunksInfo) {
        const dt = chunk?.doc_type || 'N/A';
        byRagDocType[dt] = (byRagDocType[dt] || 0) + 1;
      }
    } else {
      withoutRag += 1;
      byModelRag[model].withoutRag += 1;
    }

    const preview = norm.userPreview || `#${log.id}`;
    if (typeof norm.latency_ms === 'number') {
      withLatency.push({ id: log.id, value: norm.latency_ms, label: preview, log });
    }
    if (typeof norm.prompt_tokens === 'number') {
      withPromptTokens.push({ id: log.id, value: norm.prompt_tokens, label: preview, log });
    }
    if (typeof norm.completion_tokens === 'number') {
      withCompletionTokens.push({ id: log.id, value: norm.completion_tokens, label: preview, log });
    }
    if (typeof norm.total_tokens === 'number') {
      withTotalTokens.push({ id: log.id, value: norm.total_tokens, label: preview, log });
    }

    const d = parseLogDate(log);
    const bk = bucketKeyForLog(period, selectedDate, d);
    if (bk != null && bk in byBucket) {
      if (norm.hasRag) {
        byBucket[bk].withRag += 1;
      } else {
        byBucket[bk].withoutRag += 1;
      }
      if (norm.proxyBackend === 'rag_fusion') {
        byBucket[bk].rag_fusion += 1;
      }
      if (isCloudModelName(model)) {
        byBucket[bk].cloud += 1;
      } else {
        byBucket[bk].nonCloud += 1;
      }
    }
  }

  const modelEntries = Object.entries(byModel).sort((a, b) => b[1] - a[1]);
  const modelDiverging = modelEntries.slice(0, MODEL_TOP).map(([name]) => {
    const r = byModelRag[name] || { withRag: 0, withoutRag: 0 };
    return {
      name: name.length > 22 ? `${name.slice(0, 20)}…` : name,
      nameFull: name,
      withRag: r.withRag,
      withoutRag: r.withoutRag,
    };
  });

  const autocompleteModelBars = modelEntries.slice(0, MODEL_TOP).map(([name, value]) => ({
    name: name.length > 22 ? `${name.slice(0, 20)}…` : name,
    nameFull: name,
    requests: value,
  }));

  const docTypeKeys = Object.keys(byRagDocType).sort((a, b) => byRagDocType[b] - byRagDocType[a]);
  const docTypeBars = docTypeKeys.map((k) => ({
    name: k.length > 18 ? `${k.slice(0, 16)}…` : k,
    nameFull: k,
    chunks: byRagDocType[k],
  }));

  const timeSeries = bucketKeys
    .slice()
    .sort((a, b) => (bucketOrder.get(a) ?? 0) - (bucketOrder.get(b) ?? 0))
    .map((k) => {
      const b = byBucket[k] || {
        withRag: 0,
        withoutRag: 0,
        rag_fusion: 0,
        cloud: 0,
        nonCloud: 0,
      };
      return {
        bucket: k,
        tick: shortTickLabel(period, k),
        withRag: b.withRag,
        withoutRag: b.withoutRag,
        rag_fusion: b.rag_fusion,
        cloud: b.cloud,
        nonCloud: b.nonCloud,
      };
    });

  const topLatency = [...withLatency].sort((a, b) => b.value - a.value).slice(0, TOP_N);
  const topPromptTokens = [...withPromptTokens].sort((a, b) => b.value - a.value).slice(0, TOP_N);
  const topCompletionTokens = [...withCompletionTokens].sort((a, b) => b.value - a.value).slice(0, TOP_N);
  const topTotalTokens = [...withTotalTokens].sort((a, b) => b.value - a.value).slice(0, TOP_N);

  return {
    modelDiverging,
    autocompleteModelBars,
    docTypeKeys,
    docTypeBars,
    timeSeries,
    topLatency,
    topPromptTokens,
    topCompletionTokens,
    topTotalTokens,
    totalRequests: logs.length,
    withRag,
    withoutRag,
    hasTimeSeriesData: timeSeries.some(
      (row) =>
        row.withRag !== 0 ||
        row.withoutRag !== 0 ||
        row.rag_fusion !== 0 ||
        row.cloud !== 0 ||
        row.nonCloud !== 0,
    ),
  };
}

function ProxyLogsAnalytics({
  logs,
  period,
  onPeriodChange,
  selectedDate,
  onDateSelect,
  onDateReset,
  periodLabel,
  variant = 'proxy',
  pipelineFilter = 'mixed',
  onPipelineFilterChange,
  showPipelineFilter = false,
}) {
  const isAc = variant === 'autocomplete';
  const colors = useThemeChartColors();
  const [topDetailLog, setTopDetailLog] = useState(null);

  const agg = useMemo(
    () => aggregateLogs(logs, period, selectedDate, isAc),
    [logs, period, selectedDate, isAc],
  );

  const chartTooltipStyle = {
    background: 'var(--md-sys-color-surface-container-high, #fff)',
    border: '1px solid var(--md-sys-color-outline-variant, #ccc)',
    borderRadius: 8,
    fontSize: 12,
  };

  return (
    <div
      className="proxy-logs-analytics app-card app-card--interactive"
      role="region"
      aria-label={isAc ? 'Autocomplete logs analytics' : 'Proxy logs analytics'}
    >
      <div className="proxy-logs-analytics-controls">
        <div className="coreui-pill-tablist" role="tablist" aria-label="Time period">
          {PERIODS.map((p) => (
            <button
              key={p.id}
              type="button"
              role="tab"
              aria-selected={period === p.id}
              aria-label={`Show statistics for ${p.label.toLowerCase()}`}
              className={`coreui-pill-tab ${period === p.id ? 'coreui-pill-tab-active' : ''}`}
              onClick={() => onPeriodChange(p.id)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="proxy-logs-period-label" aria-live="polite">
          For: {periodLabel}
        </div>
      </div>

      {showPipelineFilter && onPipelineFilterChange && (
        <div className="proxy-logs-pipeline-row">
          <span className="proxy-logs-pipeline-label" id="proxy-logs-pipeline-label">
            Pipeline
          </span>
          <div
            className="coreui-pill-tablist"
            role="tablist"
            aria-labelledby="proxy-logs-pipeline-label"
          >
            {PIPELINE_OPTIONS.map((p) => (
              <button
                key={p.id}
                type="button"
                role="tab"
                aria-selected={pipelineFilter === p.id}
                className={`coreui-pill-tab ${pipelineFilter === p.id ? 'coreui-pill-tab-active' : ''}`}
                onClick={() => onPipelineFilterChange(p.id)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="proxy-logs-analytics-calendar-row">
        <ProxyLogsPeriodCalendar
          selectedDate={selectedDate}
          onDateSelect={onDateSelect}
          onDateReset={onDateReset}
        />
      </div>

      <p className="proxy-logs-analytics-summary" aria-live="polite">
        {isAc ? (
          <>
            Total autocomplete requests: {agg.totalRequests}. Bar chart shows resolved Ollama model tags (no RAG on this
            path).
          </>
        ) : (
          <>
            Total requests: {agg.totalRequests}. With RAG: {agg.withRag}. Without RAG: {agg.withoutRag}.
          </>
        )}
      </p>

      <div className={`proxy-logs-charts ${isAc ? 'proxy-logs-charts--autocomplete' : ''}`}>
        {isAc ? (
          <div className="proxy-logs-chart-block" role="figure" aria-label="Models used">
            <h3 className="proxy-logs-chart-title">Models used</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={agg.autocompleteModelBars} margin={{ top: 8, right: 16, left: 0, bottom: 64 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--md-sys-color-outline-variant, #ccc)" />
                <XAxis dataKey="name" angle={-35} textAnchor="end" height={70} tick={{ fontSize: 10 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={chartTooltipStyle}
                  formatter={(value) => [value, 'Requests']}
                  labelFormatter={(_, payload) => payload?.[0]?.payload?.nameFull || ''}
                />
                <Bar dataKey="requests" fill={colors[0]} name="Requests" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <>
            <div className="proxy-logs-chart-block" role="figure" aria-label="Models used with and without RAG">
              <h3 className="proxy-logs-chart-title">Models used (RAG vs no RAG)</h3>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={agg.modelDiverging} margin={{ top: 8, right: 16, left: 8, bottom: 72 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--md-sys-color-outline-variant, #ccc)" />
                  <XAxis dataKey="name" angle={-35} textAnchor="end" height={80} tick={{ fontSize: 10 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={chartTooltipStyle}
                    formatter={(value, name) => [value, name === 'withoutRag' ? 'Without RAG' : 'With RAG']}
                    labelFormatter={(_, payload) => payload?.[0]?.payload?.nameFull || ''}
                  />
                  <Legend />
                  <Bar dataKey="withRag" name="With RAG" fill={colors[0]} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="withoutRag" name="Without RAG" fill={colors[2]} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="proxy-logs-chart-block" role="figure" aria-label="RAG chunks by doc type">
              <h3 className="proxy-logs-chart-title">RAG chunks by doc type</h3>
              {agg.docTypeBars.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={agg.docTypeBars} margin={{ top: 8, right: 16, left: 8, bottom: 72 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--md-sys-color-outline-variant, #ccc)" />
                    <XAxis dataKey="name" angle={-30} textAnchor="end" height={72} tick={{ fontSize: 10 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={chartTooltipStyle}
                      formatter={(value) => [value, 'Chunk uses']}
                      labelFormatter={(_, payload) => payload?.[0]?.payload?.nameFull || ''}
                    />
                    <Bar dataKey="chunks" name="Chunk uses" fill={colors[1]} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="proxy-logs-chart-empty">No RAG chunk data in this range.</p>
              )}
            </div>

            <div className="proxy-logs-chart-block" role="figure" aria-label="RAG vs without RAG over time">
              <h3 className="proxy-logs-chart-title">RAG vs without RAG (by time)</h3>
              {agg.hasTimeSeriesData ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={agg.timeSeries} margin={{ top: 8, right: 16, left: 8, bottom: period === 'day' ? 48 : 32 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--md-sys-color-outline-variant, #ccc)" />
                    <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={chartTooltipStyle} />
                    <Legend />
                    <Bar dataKey="withRag" name="With RAG" stackId="ragt" fill={colors[0]} />
                    <Bar dataKey="withoutRag" name="Without RAG" stackId="ragt" fill={colors[3]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="proxy-logs-chart-empty">No time-bucket data for this range.</p>
              )}
            </div>

            <div className="proxy-logs-chart-block proxy-logs-chart-block--wide" role="figure" aria-label="RAG Fusion pipeline requests by time">
              <h3 className="proxy-logs-chart-title">RAG Fusion pipeline (by time)</h3>
              {agg.hasTimeSeriesData ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={agg.timeSeries} margin={{ top: 8, right: 16, left: 8, bottom: period === 'day' ? 48 : 32 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--md-sys-color-outline-variant, #ccc)" />
                    <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={chartTooltipStyle} />
                    <Legend />
                    <Bar dataKey="rag_fusion" name="RAG Fusion" fill={colors[4] || colors[0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="proxy-logs-chart-empty">No pipeline-tagged requests in this range.</p>
              )}
            </div>

            <div className="proxy-logs-chart-block proxy-logs-chart-block--wide" role="figure" aria-label="Cloud vs non-cloud models">
              <h3 className="proxy-logs-chart-title">Model suffix cloud vs other (by time)</h3>
              {agg.hasTimeSeriesData ? (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={agg.timeSeries} margin={{ top: 8, right: 16, left: 8, bottom: period === 'day' ? 48 : 32 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--md-sys-color-outline-variant, #ccc)" />
                    <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={chartTooltipStyle} />
                    <Legend />
                    {/* Primary vs tertiary (theme indices 0/1); dash + shape differ if tokens are still close */}
                    <Line
                      type="monotone"
                      dataKey="cloud"
                      name="Ends with cloud"
                      stroke={colors[0] || '#1a73e8'}
                      strokeWidth={2.5}
                      dot={{ r: 3, strokeWidth: 2, fill: colors[0] || '#1a73e8', stroke: colors[0] || '#1a73e8' }}
                      activeDot={{ r: 5 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="nonCloud"
                      name="Other models"
                      stroke={colors[1] || '#7b2cbf'}
                      strokeWidth={2.5}
                      strokeDasharray="7 5"
                      dot={{ r: 3, strokeWidth: 2, fill: 'var(--md-sys-color-surface, #fff)', stroke: colors[1] || '#7b2cbf' }}
                      activeDot={{ r: 5 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="proxy-logs-chart-empty">No requests in this range.</p>
              )}
            </div>
          </>
        )}
      </div>

      <div className="proxy-logs-tops">
        <div className="proxy-logs-top-block" role="region" aria-label="Top latency">
          <h3 className="proxy-logs-top-title">Top latency (ms)</h3>
          <ul className="proxy-logs-top-list">
            {agg.topLatency.length === 0 ? (
              <li className="proxy-logs-top-empty">No data</li>
            ) : (
              agg.topLatency.map((item, idx) => (
                <li key={`${item.id}-${idx}`}>
                  <button
                    type="button"
                    className="proxy-logs-top-row"
                    onClick={() => item.log && setTopDetailLog(item.log)}
                    disabled={!item.log}
                    title="Open full request / trace detail"
                  >
                    <span className="proxy-logs-top-value">{item.value} ms</span>
                    <span className="proxy-logs-top-label">{item.label || `#${item.id}`}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="proxy-logs-top-block" role="region" aria-label="Top prompt tokens">
          <h3 className="proxy-logs-top-title">Top prompt tokens</h3>
          <ul className="proxy-logs-top-list">
            {agg.topPromptTokens.length === 0 ? (
              <li className="proxy-logs-top-empty">No data</li>
            ) : (
              agg.topPromptTokens.map((item, idx) => (
                <li key={`${item.id}-${idx}`}>
                  <button
                    type="button"
                    className="proxy-logs-top-row"
                    onClick={() => item.log && setTopDetailLog(item.log)}
                    disabled={!item.log}
                    title="Open full request / trace detail"
                  >
                    <span className="proxy-logs-top-value">{item.value}</span>
                    <span className="proxy-logs-top-label">{item.label || `#${item.id}`}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="proxy-logs-top-block" role="region" aria-label="Top completion tokens">
          <h3 className="proxy-logs-top-title">Top completion tokens</h3>
          <ul className="proxy-logs-top-list">
            {agg.topCompletionTokens.length === 0 ? (
              <li className="proxy-logs-top-empty">No data</li>
            ) : (
              agg.topCompletionTokens.map((item, idx) => (
                <li key={`${item.id}-${idx}`}>
                  <button
                    type="button"
                    className="proxy-logs-top-row"
                    onClick={() => item.log && setTopDetailLog(item.log)}
                    disabled={!item.log}
                    title="Open full request / trace detail"
                  >
                    <span className="proxy-logs-top-value">{item.value}</span>
                    <span className="proxy-logs-top-label">{item.label || `#${item.id}`}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="proxy-logs-top-block" role="region" aria-label="Top total tokens">
          <h3 className="proxy-logs-top-title">Top total tokens</h3>
          <ul className="proxy-logs-top-list">
            {agg.topTotalTokens.length === 0 ? (
              <li className="proxy-logs-top-empty">No data</li>
            ) : (
              agg.topTotalTokens.map((item, idx) => (
                <li key={`${item.id}-${idx}`}>
                  <button
                    type="button"
                    className="proxy-logs-top-row"
                    onClick={() => item.log && setTopDetailLog(item.log)}
                    disabled={!item.log}
                    title="Open full request / trace detail"
                  >
                    <span className="proxy-logs-top-value">{item.value}</span>
                    <span className="proxy-logs-top-label">{item.label || `#${item.id}`}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>

      <ProxyTraceDetailModal
        log={topDetailLog}
        isOpen={Boolean(topDetailLog)}
        onClose={() => setTopDetailLog(null)}
      />
    </div>
  );
}

export default ProxyLogsAnalytics;
