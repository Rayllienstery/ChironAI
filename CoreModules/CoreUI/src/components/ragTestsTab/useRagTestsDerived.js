import { useMemo } from 'react';
import {
  groundingOverlap,
  metricVersionLabel,
  ragRetrieved,
  strictRagOk,
  yesNo,
} from './helpers';

export function useRagTestsDerived({
  runHistoryModal,
  runCompareModal,
  compareOnlyDiff,
  compareFocus,
  displayResults,
}) {
  const runHistoryResults = runHistoryModal?.run?.results || [];

  const computeStats = (values) => {
    const nums = (values || [])
      .map((v) => Number(v))
      .filter((n) => Number.isFinite(n) && n >= 0);
    if (!nums.length) return null;
    const sorted = [...nums].sort((a, b) => a - b);
    const pick = (p) => {
      const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * p)));
      return sorted[idx];
    };
    const sum = sorted.reduce((acc, n) => acc + n, 0);
    return {
      count: sorted.length,
      avg: sum / sorted.length,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      p50: pick(0.5),
      p95: pick(0.95),
    };
  };

  const latencyStatsMs = computeStats(
    runHistoryResults.map((r) => r.latency_ms ?? r.response_time_ms).filter((v) => v != null)
  );
  const stageAvg = (key) => {
    const vals = runHistoryResults
      .map((r) => (r?.rag_timings && typeof r.rag_timings === 'object' ? r.rag_timings[key] : null))
      .filter((v) => Number.isFinite(Number(v)))
      .map((v) => Number(v));
    if (!vals.length) return null;
    return vals.reduce((acc, n) => acc + n, 0) / vals.length;
  };

  const timingAverages = [
    { label: 'embed', value: stageAvg('embed_s') },
    { label: 'search', value: stageAvg('search_s') },
    { label: 'rerank', value: stageAvg('rerank_s') },
    { label: 'rag', value: stageAvg('total_rag_s') },
    { label: 'chat', value: stageAvg('chat_s_estimated') },
    { label: 'total', value: stageAvg('latency_s_total') },
  ];

  const withLatency = runHistoryResults
    .map((r) => ({
      test_id: r.test_id,
      test_name: r.test_name,
      latency_ms: Number(r.latency_ms ?? r.response_time_ms ?? NaN),
      status: r.status,
    }))
    .filter((x) => Number.isFinite(x.latency_ms))
    .sort((a, b) => a.latency_ms - b.latency_ms);
  const fastestTests = withLatency.slice(0, 5);
  const slowestTests = [...withLatency].reverse().slice(0, 5);

  const chunkMap = new Map();
  runHistoryResults.forEach((r) => {
    const chunks = Array.isArray(r?.chunks_info) ? r.chunks_info : [];
    chunks.forEach((c) => {
      const key = String(c?.url || `${c?.source || 'unknown'}:${c?.title || c?.id || c?.text_preview || ''}` || '').trim();
      if (!key) return;
      const prev = chunkMap.get(key) || { key, count: 0, scoreSum: 0, scoreCount: 0 };
      prev.count += 1;
      const s = Number(c?.score);
      if (Number.isFinite(s)) {
        prev.scoreSum += s;
        prev.scoreCount += 1;
      }
      chunkMap.set(key, prev);
    });
  });
  const topChunks = [...chunkMap.values()]
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
    .map((c) => ({ ...c, avgScore: c.scoreCount ? c.scoreSum / c.scoreCount : null }));
  const mostPopularChunk = topChunks[0] || null;

  const normalizeReason = (text) => String(text || '').trim().replace(/\s+/g, ' ').toLowerCase();
  const reasonMap = new Map();
  runHistoryResults.forEach((r) => {
    const raw = String(r?.failure_reason || r?.error || '').trim();
    if (!raw) return;
    const norm = normalizeReason(raw);
    const prev = reasonMap.get(norm) || { normalized: norm, sample: raw, count: 0, tests: [] };
    prev.count += 1;
    if (prev.tests.length < 5) prev.tests.push(r.test_name || r.test_id);
    reasonMap.set(norm, prev);
  });
  const allFailureReasons = [...reasonMap.values()].sort((a, b) => b.count - a.count);
  const topFailureReasons = allFailureReasons.slice(0, 10);
  const failureMaxCount = topFailureReasons.reduce((m, x) => Math.max(m, x.count), 1);

  const passCount = runHistoryResults.filter((r) => String(r.status || '').toUpperCase() === 'PASS').length;
  const failCount = runHistoryResults.filter((r) => String(r.status || '').toUpperCase() === 'FAIL').length;
  const ragRetrievedCount = runHistoryResults.filter((r) => ragRetrieved(r)).length;
  const groundingOverlapCount = runHistoryResults.filter((r) => groundingOverlap(r)).length;
  const strictRagOkCount = runHistoryResults.filter((r) => strictRagOk(r)).length;
  const strictRagTotal = runHistoryResults.filter((r) => r?.strict_rag_ok != null).length;
  const totalCount = runHistoryResults.length;

  const summaryBars = [
    { label: 'PASS', value: passCount },
    { label: 'FAIL', value: failCount },
    { label: 'RAG retrieved', value: ragRetrievedCount },
    { label: 'Grounding overlap', value: groundingOverlapCount },
  ];
  const summaryBarMax = summaryBars.reduce((m, x) => Math.max(m, x.value), 1);

  const formatRunDate = (iso) => {
    if (!iso) return '-';
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
    } catch {
      return iso;
    }
  };

  const compareLeftRun = runCompareModal?.left?.run || null;
  const compareRightRun = runCompareModal?.right?.run || null;
  const compareLeftResults = Array.isArray(compareLeftRun?.run?.results)
    ? compareLeftRun.run.results
    : Array.isArray(compareLeftRun?.results)
      ? compareLeftRun.results
      : [];
  const compareRightResults = Array.isArray(compareRightRun?.run?.results)
    ? compareRightRun.run.results
    : Array.isArray(compareRightRun?.results)
      ? compareRightRun.results
      : [];

  const compareCountByStatus = (rows, status) =>
    rows.filter((r) => String(r?.status || '').toUpperCase() === String(status || '').toUpperCase()).length;
  const compareRagRetrievedCount = (rows) => rows.filter((r) => ragRetrieved(r)).length;
  const compareGroundingOverlapCount = (rows) => rows.filter((r) => groundingOverlap(r)).length;
  const compareMeanLatency = (rows) => {
    const vals = rows
      .map((r) => Number(r?.latency_ms ?? r?.response_time_ms))
      .filter((v) => Number.isFinite(v) && v >= 0);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const comparePassRate = (rows) => {
    if (!rows.length) return null;
    return (compareCountByStatus(rows, 'PASS') / rows.length) * 100;
  };
  const compareTpsAvg = (rows) => {
    const vals = rows
      .map((r) => Number(r?.tokens_per_second_generated))
      .filter((v) => Number.isFinite(v) && v >= 0);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const compareSummaryRows = [
    {
      key: 'total',
      label: 'Total tests',
      left: compareLeftResults.length,
      right: compareRightResults.length,
      higherIsBetter: null,
    },
    {
      key: 'pass',
      label: 'Passed',
      left: compareCountByStatus(compareLeftResults, 'PASS'),
      right: compareCountByStatus(compareRightResults, 'PASS'),
      higherIsBetter: true,
    },
    {
      key: 'fail',
      label: 'Failed',
      left: compareCountByStatus(compareLeftResults, 'FAIL'),
      right: compareCountByStatus(compareRightResults, 'FAIL'),
      higherIsBetter: false,
    },
    {
      key: 'pass_rate',
      label: 'Pass rate %',
      left: comparePassRate(compareLeftResults),
      right: comparePassRate(compareRightResults),
      higherIsBetter: true,
    },
    {
      key: 'rag_retrieved',
      label: 'RAG retrieved',
      left: compareRagRetrievedCount(compareLeftResults),
      right: compareRagRetrievedCount(compareRightResults),
      higherIsBetter: true,
    },
    {
      key: 'grounding_overlap',
      label: 'Grounding overlap',
      left: compareGroundingOverlapCount(compareLeftResults),
      right: compareGroundingOverlapCount(compareRightResults),
      higherIsBetter: true,
    },
    {
      key: 'latency_avg',
      label: 'Avg latency (ms)',
      left: compareMeanLatency(compareLeftResults),
      right: compareMeanLatency(compareRightResults),
      higherIsBetter: false,
    },
    {
      key: 'tps_avg',
      label: 'Avg tok/s',
      left: compareTpsAvg(compareLeftResults),
      right: compareTpsAvg(compareRightResults),
      higherIsBetter: true,
    },
  ];

  const compareFmt = (v, digits = 0) => {
    if (v == null) return '-';
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v);
    return digits > 0 ? n.toFixed(digits) : String(Math.round(n));
  };
  const compareDeltaText = (left, right, higherIsBetter = null, digits = 0) => {
    const l = Number(left);
    const r = Number(right);
    if (!Number.isFinite(l) || !Number.isFinite(r)) return '·';
    const d = r - l;
    if (Math.abs(d) < 1e-9) return '±0';
    const sign = d > 0 ? '+' : '-';
    const abs = Math.abs(d);
    const body = digits > 0 ? abs.toFixed(digits) : String(Math.round(abs));
    if (higherIsBetter === true) return `${sign}${body}`;
    if (higherIsBetter === false) return `${d < 0 ? '+' : '-'}${body}`;
    return `${sign}${body}`;
  };
  const compareDeltaClass = (text) => {
    const s = String(text || '').trim();
    if (!s || s === '·' || s === '±0') return 'neutral';
    if (s.startsWith('+')) return 'positive';
    if (s.startsWith('-')) return 'negative';
    return 'neutral';
  };
  const parseConfidenceLabel = (label) => {
    const m = String(label || '').match(/^\s*(\d+)\s*\/\s*(\d+)\s*$/);
    if (!m) return null;
    const found = Number(m[1]);
    const total = Number(m[2]);
    if (!Number.isFinite(found) || !Number.isFinite(total) || total <= 0) return null;
    return { found, total, ratio: found / total };
  };
  const compareConfidenceDeltaText = (left, right) => {
    const lc = parseConfidenceLabel(left?.confidence_label);
    const rc = parseConfidenceLabel(right?.confidence_label);
    if (!lc || !rc) return '·';
    if (lc.found === rc.found && lc.total === rc.total) return '±0';
    if (lc.total === rc.total) {
      const d = rc.found - lc.found;
      const sign = d > 0 ? '+' : '-';
      return `${sign}${Math.abs(d)}/${rc.total}`;
    }
    return `${lc.found}/${lc.total}→${rc.found}/${rc.total}`;
  };
  const compareTpsDeltaText = (left, right) => {
    const lt = Number(left?.tokens_per_second_generated);
    const rt = Number(right?.tokens_per_second_generated);
    if (!Number.isFinite(lt) || !Number.isFinite(rt)) return '·';
    return compareDeltaText(lt, rt, true, 2);
  };
  const compareSelectedDeltaText = (left, right, statusDelta, latencyDelta) => {
    if (compareFocus === 'status') return statusDelta;
    if (compareFocus === 'latency') return latencyDelta;
    if (compareFocus === 'tps') return compareTpsDeltaText(left, right);
    if (compareFocus === 'confidence') return compareConfidenceDeltaText(left, right);
    return statusDelta;
  };

  const compareHasTestDiff = (left, right) => {
    if (!left || !right) return true;

    if (compareFocus === 'status') {
      const ls = String(left?.status || '').toUpperCase();
      const rs = String(right?.status || '').toUpperCase();
      return ls !== rs;
    }

    if (compareFocus === 'latency') {
      const ll = Number(left?.latency_ms ?? left?.response_time_ms);
      const rl = Number(right?.latency_ms ?? right?.response_time_ms);
      if (Number.isFinite(ll) !== Number.isFinite(rl)) return true;
      if (!Number.isFinite(ll) || !Number.isFinite(rl)) return false;
      return Math.round(ll) !== Math.round(rl);
    }

    if (compareFocus === 'tps') {
      const lt = Number(left?.tokens_per_second_generated);
      const rt = Number(right?.tokens_per_second_generated);
      if (Number.isFinite(lt) !== Number.isFinite(rt)) return true;
      if (!Number.isFinite(lt) || !Number.isFinite(rt)) return false;
      return Math.abs(lt - rt) > 0.01;
    }

    if (compareFocus === 'confidence') {
      const lc = parseConfidenceLabel(left?.confidence_label);
      const rc = parseConfidenceLabel(right?.confidence_label);
      if (!lc && !rc) return false;
      if (!lc || !rc) return true;
      return lc.found !== rc.found || lc.total !== rc.total;
    }

    return false;
  };

  const testMatchKey = (row, idx) => {
    const id = String(row?.test_id || '').trim();
    if (id) return `id:${id}`;
    const name = String(row?.test_name || '').trim().toLowerCase();
    if (name) return `name:${name}`;
    return `row:${idx}`;
  };
  const bucketByTestKey = (rows) => {
    const out = new Map();
    rows.forEach((r, idx) => {
      const key = testMatchKey(r, idx);
      if (!out.has(key)) out.set(key, []);
      out.get(key).push(r);
    });
    return out;
  };
  const leftBuckets = bucketByTestKey(compareLeftResults);
  const rightBuckets = bucketByTestKey(compareRightResults);
  const allBucketKeys = [...new Set([...leftBuckets.keys(), ...rightBuckets.keys()])];
  const comparePairs = [];
  allBucketKeys.forEach((k) => {
    const leftRows = leftBuckets.get(k) || [];
    const rightRows = rightBuckets.get(k) || [];
    const maxLen = Math.max(leftRows.length, rightRows.length);
    for (let i = 0; i < maxLen; i += 1) {
      comparePairs.push({
        pairKey: `${k}#${i}`,
        left: leftRows[i] || null,
        right: rightRows[i] || null,
      });
    }
  });
  const comparePairRank = (pair) => {
    const left = pair?.left || null;
    const right = pair?.right || null;
    const leftStatus = String(left?.status || '-').toUpperCase();
    const rightStatus = String(right?.status || '-').toUpperCase();
    const leftLatency = Number(left?.latency_ms ?? left?.response_time_ms);
    const rightLatency = Number(right?.latency_ms ?? right?.response_time_ms);
    const leftTps = Number(left?.tokens_per_second_generated);
    const rightTps = Number(right?.tokens_per_second_generated);
    const leftConf = parseConfidenceLabel(left?.confidence_label);
    const rightConf = parseConfidenceLabel(right?.confidence_label);

    if (compareFocus === 'status') {
      let rank = 0;
      if (!left || !right) rank += 200;
      if (leftStatus !== rightStatus) rank += 150;
      if (leftStatus === 'FAIL' || rightStatus === 'FAIL') rank += 120;
      if (leftStatus === 'PASS' && rightStatus === 'PASS') rank += 20;
      return rank;
    }
    if (compareFocus === 'latency') {
      if (!Number.isFinite(leftLatency) || !Number.isFinite(rightLatency)) return -1;
      return Math.abs(rightLatency - leftLatency);
    }
    if (compareFocus === 'tps') {
      if (!Number.isFinite(leftTps) || !Number.isFinite(rightTps)) return -1;
      return Math.abs(rightTps - leftTps);
    }
    if (compareFocus === 'confidence') {
      if (!leftConf || !rightConf) return -1;
      const ratioDiff = Math.abs((rightConf.ratio - leftConf.ratio) * 100);
      const foundDiff = Math.abs(rightConf.found - leftConf.found);
      return ratioDiff + foundDiff;
    }
    return 0;
  };
  const compareVisiblePairs = compareOnlyDiff
    ? comparePairs.filter((p) => compareHasTestDiff(p.left, p.right))
    : comparePairs;
  const compareRenderedPairs = [...compareVisiblePairs].sort((a, b) => {
    const ra = comparePairRank(a);
    const rb = comparePairRank(b);
    if (rb !== ra) return rb - ra;
    const la = String(a?.left?.test_name || a?.right?.test_name || a?.pairKey || '');
    const lb = String(b?.left?.test_name || b?.right?.test_name || b?.pairKey || '');
    return la.localeCompare(lb);
  });

  return {
    runHistoryResults,
    latencyStatsMs,
    stageAvg,
    timingAverages,
    fastestTests,
    slowestTests,
    topChunks,
    mostPopularChunk,
    allFailureReasons,
    topFailureReasons,
    failureMaxCount,
    passCount,
    failCount,
    ragRetrievedCount,
    groundingOverlapCount,
    strictRagOkCount,
    strictRagTotal,
    totalCount,
    summaryBars,
    summaryBarMax,
    formatRunDate,
    compareLeftRun,
    compareRightRun,
    compareLeftResults,
    compareRightResults,
    compareSummaryRows,
    compareFmt,
    compareDeltaText,
    compareDeltaClass,
    compareConfidenceDeltaText,
    compareTpsDeltaText,
    compareSelectedDeltaText,
    compareHasTestDiff,
    compareVisiblePairs,
    compareRenderedPairs,
  };
}
