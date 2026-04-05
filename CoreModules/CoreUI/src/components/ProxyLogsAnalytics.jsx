import React from 'react';
import {
  PieChart,
  Pie,
  Cell,
  Legend,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { useThemeChartColors } from '../hooks/useThemeChartColors';
import ProxyLogsPeriodCalendar from './ProxyLogsPeriodCalendar';
import '../styles/components/CoreUIPillTabs.css';

const PERIODS = [
  { id: 'day', label: 'Day' },
  { id: 'week', label: 'Week' },
  { id: 'month', label: 'Month' },
  { id: 'year', label: 'Year' },
  { id: 'all', label: 'All time' },
];

const TOP_N = 10;
const MODEL_PIE_TOP = 8;

function getMetadata(log) {
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

function aggregateLogs(logsInput) {
  const logs = Array.isArray(logsInput) ? logsInput : [];
  const byModel = {};
  const byRagDocType = {};
  let withRag = 0;
  let withoutRag = 0;
  const withLatency = [];
  const withPromptTokens = [];
  const withCompletionTokens = [];
  const withTotalTokens = [];

  for (const log of logs) {
    const meta = getMetadata(log);
    const model = meta.model || 'N/A';
    byModel[model] = (byModel[model] || 0) + 1;

    const ragContext = meta.rag_context;
    const chunksInfo = Array.isArray(ragContext?.chunks_info) ? ragContext.chunks_info : [];
    const hasRag = (ragContext?.chunks_count > 0) || chunksInfo.length > 0;
    if (hasRag) {
      withRag += 1;
      for (const chunk of chunksInfo) {
        const dt = chunk?.doc_type || 'N/A';
        byRagDocType[dt] = (byRagDocType[dt] || 0) + 1;
      }
    } else {
      withoutRag += 1;
    }

    const latency = meta.latency_ms;
    const promptTokens = meta.prompt_tokens;
    const completionTokens = meta.completion_tokens;
    const totalTokens = meta.total_tokens;
    const preview = (meta.user_query || '').slice(0, 40);
    if (typeof latency === 'number') {
      withLatency.push({ id: log.id, value: latency, label: preview || `#${log.id}` });
    }
    if (typeof promptTokens === 'number') {
      withPromptTokens.push({ id: log.id, value: promptTokens, label: preview || `#${log.id}` });
    }
    if (typeof completionTokens === 'number') {
      withCompletionTokens.push({ id: log.id, value: completionTokens, label: preview || `#${log.id}` });
    }
    if (typeof totalTokens === 'number') {
      withTotalTokens.push({ id: log.id, value: totalTokens, label: preview || `#${log.id}` });
    }
  }

  const modelEntries = Object.entries(byModel)
    .sort((a, b) => b[1] - a[1]);
  const modelPieData = modelEntries.length <= MODEL_PIE_TOP
    ? modelEntries.map(([name, value]) => ({ name, value }))
    : [
        ...modelEntries.slice(0, MODEL_PIE_TOP).map(([name, value]) => ({ name, value })),
        { name: 'Other', value: modelEntries.slice(MODEL_PIE_TOP).reduce((s, [, v]) => s + v, 0) },
      ];

  const ragDocTypeData = Object.entries(byRagDocType)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }));

  const ragVsNoRagData = [
    { name: 'With RAG', value: withRag },
    { name: 'Without RAG', value: withoutRag },
  ].filter((d) => d.value > 0);

  const topLatency = [...withLatency].sort((a, b) => b.value - a.value).slice(0, TOP_N);
  const topPromptTokens = [...withPromptTokens].sort((a, b) => b.value - a.value).slice(0, TOP_N);
  const topCompletionTokens = [...withCompletionTokens].sort((a, b) => b.value - a.value).slice(0, TOP_N);
  const topTotalTokens = [...withTotalTokens].sort((a, b) => b.value - a.value).slice(0, TOP_N);

  return {
    modelPieData: modelPieData.length ? modelPieData : [{ name: 'No data', value: 1 }],
    ragDocTypeData: ragDocTypeData.length ? ragDocTypeData : [{ name: 'No RAG chunks', value: 1 }],
    ragVsNoRagData: ragVsNoRagData.length ? ragVsNoRagData : [{ name: 'No data', value: 1 }],
    topLatency,
    topPromptTokens,
    topCompletionTokens,
    topTotalTokens,
    totalRequests: logs.length,
    withRag,
    withoutRag,
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
}) {
  const agg = aggregateLogs(logs);
  const isAc = variant === 'autocomplete';
  const pieColors = useThemeChartColors();

  return (
    <div
      className="proxy-logs-analytics"
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
            Total autocomplete requests: {agg.totalRequests}. Pie chart shows resolved Ollama model tags (no RAG on this
            path).
          </>
        ) : (
          <>
            Total requests: {agg.totalRequests}. With RAG: {agg.withRag}. Without RAG: {agg.withoutRag}.
          </>
        )}
      </p>

      <div className={`proxy-logs-pies ${isAc ? 'proxy-logs-pies--autocomplete' : ''}`}>
        <div className="proxy-logs-pie-block" role="figure" aria-label="Models used">
          <h3 className="proxy-logs-pie-title">Models used</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={agg.modelPieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={70}
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
              >
                {agg.modelPieData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => [value, 'Requests']} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {!isAc && (
          <>
            <div className="proxy-logs-pie-block" role="figure" aria-label="RAG chunks by doc type">
              <h3 className="proxy-logs-pie-title">RAG chunks by doc type</h3>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={agg.ragDocTypeData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {agg.ragDocTypeData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [value, 'Chunk uses']} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="proxy-logs-pie-block" role="figure" aria-label="RAG vs without RAG">
              <h3 className="proxy-logs-pie-title">RAG vs without RAG</h3>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={agg.ragVsNoRagData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {agg.ragVsNoRagData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [value, 'Requests']} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
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
                  <span className="proxy-logs-top-value">{item.value} ms</span>
                  <span className="proxy-logs-top-label" title={item.label}>{item.label || `#${item.id}`}</span>
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
                  <span className="proxy-logs-top-value">{item.value}</span>
                  <span className="proxy-logs-top-label" title={item.label}>{item.label || `#${item.id}`}</span>
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
                  <span className="proxy-logs-top-value">{item.value}</span>
                  <span className="proxy-logs-top-label" title={item.label}>{item.label || `#${item.id}`}</span>
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
                  <span className="proxy-logs-top-value">{item.value}</span>
                  <span className="proxy-logs-top-label" title={item.label}>{item.label || `#${item.id}`}</span>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}

export default ProxyLogsAnalytics;
