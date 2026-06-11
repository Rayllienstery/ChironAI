import assert from 'node:assert/strict';

globalThis.window = {
  setTimeout,
  clearTimeout,
};

const {
  getModuleTimings,
  loadTrackedModule,
} = await import('../src/services/moduleTimings.js');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function findTiming(id) {
  return getModuleTimings().find((record) => record.id === id);
}

async function testPrefetchCanGoStaleWithoutBreakingNavigation() {
  let resolveImport;
  const importer = () => new Promise((resolve) => {
    resolveImport = () => resolve({ default: 'SlowPrefetchTab' });
  });

  void loadTrackedModule('SlowPrefetchTab', importer, {
    source: 'idle prefetch',
    timeoutMs: 0,
    staleAfterMs: 20,
  });

  await sleep(40);
  let record = findTiming('SlowPrefetchTab');
  assert.equal(record.status, 'skipped');
  assert.equal(record.step, 'prefetch pending in background');

  const navigation = loadTrackedModule('SlowPrefetchTab', importer, {
    source: 'navigation',
    timeoutMs: 100,
  });
  record = findTiming('SlowPrefetchTab');
  assert.equal(record.status, 'in_progress');
  assert.equal(record.step, 'awaiting existing import');

  resolveImport();
  await navigation;

  record = findTiming('SlowPrefetchTab');
  assert.equal(record.status, 'ok');
  assert.deepEqual(record.sources, ['idle prefetch', 'navigation']);
}

async function testNavigationTimeoutIsPerCaller() {
  await assert.rejects(
    loadTrackedModule('NeverResolvesTab', () => new Promise(() => {}), {
      source: 'navigation',
      timeoutMs: 20,
    }),
    /Timed out dynamically importing NeverResolvesTab after 20ms/,
  );

  const record = findTiming('NeverResolvesTab');
  assert.equal(record.status, 'failed');
  assert.equal(record.step, 'timed out');
}

async function testResolvedImportDoesNotReturnToInProgress() {
  let importCalls = 0;
  const importer = () => {
    importCalls += 1;
    return Promise.resolve({ default: 'ExtensionRuntimeTab' });
  };

  await loadTrackedModule('ExtensionRuntimeTab', importer, {
    source: 'extension surface',
    timeoutMs: 100,
  });

  let record = findTiming('ExtensionRuntimeTab');
  assert.equal(record.status, 'ok');
  assert.equal(record.step, 'resolved');

  await loadTrackedModule('ExtensionRuntimeTab', importer, {
    source: 'navigation',
    timeoutMs: 100,
  });

  record = findTiming('ExtensionRuntimeTab');
  assert.equal(record.status, 'ok');
  assert.equal(record.step, 'resolved');
  assert.equal(importCalls, 2);
}

await testPrefetchCanGoStaleWithoutBreakingNavigation();
await testNavigationTimeoutIsPerCaller();
await testResolvedImportDoesNotReturnToInProgress();

console.log('moduleTimings regression checks passed');
