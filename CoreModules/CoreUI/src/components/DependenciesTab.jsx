import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  checkDependencyUpdates,
  getDependencies,
  getDependencyJob,
  updateDependencies,
} from '../services/api';
import '../styles/components/DependenciesTab.css';
import CoreUIBadge from './CoreUIBadge';
import CoreUIButton from './CoreUIButton';
import CoreUIPillTabs from './CoreUIPillTabs';
import EmptyState from './EmptyState';
import { useOptionalNotificationCenter } from './NotificationCenterContext';

const ECOSYSTEM_TABS = [
  { id: 'all', label: 'All' },
  { id: 'python', label: 'Python' },
  { id: 'npm', label: 'CoreUI npm' },
  { id: 'docker', label: 'Docker' },
];

const STATUS_TABS = [
  { id: 'all', label: 'All states' },
  { id: 'installed', label: 'Installed' },
  { id: 'missing', label: 'Missing' },
  { id: 'declared', label: 'Declared' },
];

const LIVE_ACTIVITY_ID = 'dependencies-update';

const PHASE_LABELS = {
  starting: 'Preparing',
  preparing: 'Preparing',
  downloading: 'Downloading',
  downloaded: 'Verifying download',
  installing: 'Installing',
  verifying: 'Verifying',
  uninstalling: 'Removing old version',
  reify: 'Installing',
  add: 'Adding package',
  change: 'Updating package',
  remove: 'Removing package',
  idealTree: 'Resolving tree',
  done: 'Completed',
  timeout: 'Timed out',
  'spawn-failed': 'Failed to start',
  failed: 'Failed',
};

function formatDate(value) {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusTone(status) {
  if (status === 'installed') return 'success';
  if (status === 'missing') return 'error';
  if (status === 'declared') return 'info';
  return 'neutral';
}

function ecosystemIcon(ecosystem) {
  if (ecosystem === 'python') return 'data_object';
  if (ecosystem === 'npm') return 'deployed_code';
  if (ecosystem === 'docker') return 'deployed_code_account';
  return 'inventory_2';
}

function commandLabel(job) {
  if (!job) return '';
  if (job.mode === 'check') return 'Checking updates';
  return 'Updating dependencies';
}

function getUpdates(job) {
  const updates = job?.result?.updates;
  return Array.isArray(updates) ? updates : [];
}

function getUpdatedPackages(job) {
  const items = job?.result?.updated_packages;
  if (Array.isArray(items) && items.length > 0) return items;
  return Array.isArray(job?.updated_packages) ? job.updated_packages : [];
}

function getFailedSteps(job) {
  return (job?.steps || []).filter((step) => !step.ok);
}

function sourceText(dep) {
  const sources = dep.sources || [];
  if (sources.length === 0) return 'No source';
  const first = sources[0];
  const suffix = sources.length > 1 ? ` +${sources.length - 1}` : '';
  return `${first.path}${first.group ? `:${first.group}` : ''}${suffix}`;
}

function phaseLabel(phase) {
  if (!phase) return '';
  return PHASE_LABELS[phase] || phase;
}

function formatUpdateList(packages) {
  return packages
    .map((entry) => {
      const name = entry?.name || '';
      if (!name) return '';
      const current = entry?.current ? entry.current : null;
      const nextVersion = entry?.next_version || entry?.latest || null;
      if (current && nextVersion) return `${name} (${current} → ${nextVersion})`;
      if (current) return `${name} (was ${current})`;
      if (nextVersion) return `${name} (→ ${nextVersion})`;
      return name;
    })
    .filter(Boolean);
}

function formatNotificationList(packages) {
  return formatUpdateList(packages)
    .map((line) => `● ${line}`)
    .join('\n');
}

function DependencyLivePanel({ job, completed }) {
  const phase = phaseLabel(job?.current_phase);
  const pkg = job?.current_package || '';
  const ecosystem = job?.current_ecosystem || '';
  const last = completed.length > 0 ? completed[completed.length - 1] : null;
  return (
    <div className="dependencies-live-panel">
      <div className="dependencies-live-panel-row">
        <span className="dependencies-live-panel-label">Ecosystem</span>
        <strong>{ecosystem || '—'}</strong>
      </div>
      <div className="dependencies-live-panel-row">
        <span className="dependencies-live-panel-label">Phase</span>
        <strong>{phase || 'Starting'}</strong>
      </div>
      <div className="dependencies-live-panel-row">
        <span className="dependencies-live-panel-label">Package</span>
        <strong>{pkg || '—'}</strong>
      </div>
      <div className="dependencies-live-panel-row">
        <span className="dependencies-live-panel-label">Updated</span>
        <strong>{completed.length}</strong>
      </div>
      {last?.name ? (
        <div className="dependencies-live-panel-last">
          <span className="material-symbols-outlined" aria-hidden="true">check_circle</span>
          <span>{last.name}</span>
        </div>
      ) : null}
    </div>
  );
}

export default function DependenciesTab() {
  const notificationCenter = useOptionalNotificationCenter();
  const persistNotification = notificationCenter?.persistNotification;
  const setLiveActivity = notificationCenter?.setLiveActivity;
  const clearLiveActivity = notificationCenter?.clearLiveActivity;
  const clearLiveSuppression = notificationCenter?.clearLiveSuppression;
  const [inventory, setInventory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [ecosystem, setEcosystem] = useState('all');
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  const [job, setJob] = useState(null);
  const notifiedJobRef = useRef(null);

  const loadInventory = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getDependencies();
      setInventory(data);
    } catch (err) {
      const message = err?.message || 'Failed to load dependencies';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadInventory();
  }, [loadInventory]);

  useEffect(() => {
    if (!job?.id || !['queued', 'running'].includes(job.status)) return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await getDependencyJob(job.id);
        if (!cancelled) setJob(data.job);
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Failed to poll dependency job');
      }
    };
    const timer = window.setInterval(poll, 1500);
    poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.id, job?.status]);

  useEffect(() => {
    if (!job?.id || !['succeeded', 'failed'].includes(job.status)) return;
    if (notifiedJobRef.current === job.id) return;
    notifiedJobRef.current = job.id;

    const failedSteps = getFailedSteps(job);
    const updates = getUpdates(job);
    const updatedPackages = getUpdatedPackages(job);
    if (persistNotification) {
      const isCheck = job.mode === 'check';
      const ok = job.status === 'succeeded';
      const lines = [];
      let summary;
      if (isCheck) {
        summary =
          updates.length === 0
            ? 'No dependency updates reported.'
            : `${updates.length} dependency update${updates.length === 1 ? '' : 's'} available.`;
      } else {
        const done = updatedPackages.filter((entry) => entry.status === 'done');
        if (ok) {
          if (done.length === 0) {
            summary = 'Dependency update job finished.';
          } else {
            summary = `Updated ${done.length} package${done.length === 1 ? '' : 's'}:`;
            lines.push(...formatNotificationList(done).split('\n'));
          }
        } else {
          summary = `${failedSteps.length || 1} dependency step failed.`;
        }
      }
      void persistNotification({
        kind: ok ? 'info' : 'error',
        source: 'dependencies',
        title: isCheck ? 'Dependency update check' : 'Dependency update',
        message: lines.length > 0 ? `${summary}\n${lines.join('\n')}` : summary,
        metadata: {
          job_id: job.id,
          mode: job.mode,
          status: job.status,
          updated_count: updatedPackages.filter((entry) => entry.status === 'done').length,
        },
        aggregation_key: `dependencies|${job.mode}|${job.id}`,
      });
    }
    if (job.mode === 'update_all' && job.status === 'succeeded') {
      void loadInventory();
    }
  }, [job, loadInventory, persistNotification]);

  const running = job && ['queued', 'running'].includes(job.status);
  const completedPackages = Array.isArray(job?.updated_packages) ? job.updated_packages : [];

  useEffect(() => {
    if (!setLiveActivity || !clearLiveActivity) return undefined;
    if (!running || !job) {
      clearLiveActivity(LIVE_ACTIVITY_ID);
      return undefined;
    }
    clearLiveSuppression?.(LIVE_ACTIVITY_ID);
    setLiveActivity(
      LIVE_ACTIVITY_ID,
      'dependencies',
      <DependencyLivePanel job={job} completed={completedPackages} />,
      {
        headerLeading: (
          <span className="dependencies-live-panel-header">
            <span
              className="dependencies-live-panel-spinner"
              aria-hidden="true"
            />
            <span>{job.mode === 'check' ? 'Dependency check' : 'Dependency update'}</span>
          </span>
        ),
      },
    );
    return undefined;
  }, [
    running,
    job,
    completedPackages,
    setLiveActivity,
    clearLiveActivity,
    clearLiveSuppression,
  ]);

  useEffect(() => () => clearLiveActivity?.(LIVE_ACTIVITY_ID), [clearLiveActivity]);

  const dependencies = inventory?.dependencies || [];
  const counts = inventory?.counts || {};
  const filteredDependencies = useMemo(() => {
    const q = query.trim().toLowerCase();
    return dependencies.filter((dep) => {
      if (ecosystem !== 'all' && dep.ecosystem !== ecosystem) return false;
      if (status !== 'all' && dep.status !== status) return false;
      if (!q) return true;
      const haystack = [
        dep.name,
        dep.requested,
        dep.installed_version,
        dep.manager,
        ...(dep.sources || []).flatMap((source) => [source.path, source.group]),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [dependencies, ecosystem, query, status]);

  const updates = getUpdates(job);
  const failedSteps = getFailedSteps(job);

  const startJob = useCallback(
    async (mode) => {
      if (mode === 'update_all') {
        const confirmed = window.confirm(
          'Update Python and CoreUI npm dependencies now? This can change installed packages and lockfiles.',
        );
        if (!confirmed) return;
      }
      setError('');
      notifiedJobRef.current = null;
      try {
        const data = mode === 'check' ? await checkDependencyUpdates() : await updateDependencies();
        setJob(data.job);
        if (persistNotification) {
          void persistNotification({
            kind: 'info',
            source: 'dependencies',
            title: mode === 'check' ? 'Dependency update check started' : 'Dependency update started',
            message:
              mode === 'check'
                ? 'Checking Python and CoreUI npm packages for newer versions.'
                : 'Running Python and CoreUI npm dependency updates.',
            metadata: { job_id: data.job?.id, mode },
            aggregation_key: `dependencies|${mode}|started`,
          });
        }
      } catch (err) {
        const message = err?.message || 'Failed to start dependency job';
        setError(message);
        if (persistNotification) {
          void persistNotification({
            kind: 'error',
            source: 'dependencies',
            title: 'Dependency action failed',
            message,
            aggregation_key: `dependencies|${mode}|failed-start`,
          });
        }
      }
    },
    [persistNotification],
  );

  return (
    <div className="dependencies-tab">
      <header className="dependencies-hero">
        <div>
          <span className="dependencies-kicker">Third-party dependencies</span>
          <h1>Dependencies</h1>
        </div>
        <div className="dependencies-actions">
          <CoreUIButton onClick={loadInventory} disabled={loading || running}>
            <span className="material-symbols-outlined" aria-hidden="true">refresh</span>
            Refresh
          </CoreUIButton>
          <CoreUIButton onClick={() => startJob('check')} disabled={running}>
            <span className="material-symbols-outlined" aria-hidden="true">manage_search</span>
            Check
          </CoreUIButton>
          <CoreUIButton variant="primary" onClick={() => startJob('update_all')} disabled={running}>
            <span className="material-symbols-outlined" aria-hidden="true">upgrade</span>
            Update all
          </CoreUIButton>
        </div>
      </header>

      {error ? (
        <div className="coreui-panel-note coreui-panel-note--error" role="alert">{error}</div>
      ) : null}

      <section className="dependencies-summary" aria-label="Dependency summary">
        <div className="dependencies-stat">
          <span className="dependencies-stat-label">Direct</span>
          <strong>{counts.total ?? 0}</strong>
        </div>
        <div className="dependencies-stat">
          <span className="dependencies-stat-label">Installed</span>
          <strong>{counts.installed ?? 0}</strong>
        </div>
        <div className="dependencies-stat dependencies-stat--warn">
          <span className="dependencies-stat-label">Missing</span>
          <strong>{counts.missing ?? 0}</strong>
        </div>
        <div className="dependencies-stat">
          <span className="dependencies-stat-label">Files</span>
          <strong>{inventory?.files?.length ?? 0}</strong>
        </div>
      </section>

      <section className="dependencies-update-panel" aria-label="Dependency updates">
        <div className="dependencies-update-main">
          <div className={`dependencies-job-orb dependencies-job-orb--${job?.status || 'idle'}`}>
            <span className="material-symbols-outlined" aria-hidden="true">
              {running ? 'progress_activity' : job?.status === 'failed' ? 'error' : 'task_alt'}
            </span>
          </div>
          <div>
            <h2>{job ? commandLabel(job) : 'Update state'}</h2>
            <p>
              {job
                ? `${job.status} - ${job.steps?.length || 0} step${job.steps?.length === 1 ? '' : 's'} - ${formatDate(job.finished_at || job.started_at || job.created_at)}`
                : `Snapshot generated ${formatDate(inventory?.generated_at)}`}
            </p>
            {running && job ? (
              <p className="dependencies-current-step">
                <span className="material-symbols-outlined" aria-hidden="true">arrow_right_alt</span>
                <span>
                  {job.current_ecosystem
                    ? `${job.current_ecosystem}: `
                    : ''}
                  {phaseLabel(job.current_phase) || 'preparing'}
                  {job.current_package ? ` — ${job.current_package}` : ''}
                </span>
              </p>
            ) : null}
            {!running && job && completedPackages.length > 0 ? (
              <p className="dependencies-current-step">
                <span className="material-symbols-outlined" aria-hidden="true">check</span>
                <span>
                  Updated {completedPackages.length} package
                  {completedPackages.length === 1 ? '' : 's'} in this run.
                </span>
              </p>
            ) : null}
          </div>
        </div>
        <div className="dependencies-update-meta">
          {updates.length > 0 ? (
            <CoreUIBadge tone="warning">{updates.length} updates</CoreUIBadge>
          ) : failedSteps.length > 0 ? (
            <CoreUIBadge tone="error">{failedSteps.length} failed</CoreUIBadge>
          ) : running ? (
            <CoreUIBadge tone="info">running</CoreUIBadge>
          ) : (
            <CoreUIBadge tone="success">ready</CoreUIBadge>
          )}
        </div>
      </section>

      {updates.length > 0 ? (
        <section className="dependencies-updates-list" aria-label="Available updates">
          {updates.slice(0, 8).map((update) => (
            <div key={`${update.ecosystem}:${update.name}`} className="dependencies-update-row">
              <span className="material-symbols-outlined" aria-hidden="true">{ecosystemIcon(update.ecosystem)}</span>
              <strong>{update.name}</strong>
              <span>{update.current || 'unknown'}</span>
              <span className="material-symbols-outlined dependencies-update-arrow" aria-hidden="true">arrow_forward</span>
              <span>{update.latest || update.wanted || 'newer'}</span>
            </div>
          ))}
        </section>
      ) : null}

      <section className="dependencies-toolbar" aria-label="Dependency filters">
        <CoreUIPillTabs tabs={ECOSYSTEM_TABS} value={ecosystem} onChange={setEcosystem} ariaLabel="Dependency ecosystem" />
        <CoreUIPillTabs tabs={STATUS_TABS} value={status} onChange={setStatus} ariaLabel="Dependency status" />
        <label className="dependencies-search">
          <span className="material-symbols-outlined" aria-hidden="true">search</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search dependencies"
          />
        </label>
      </section>

      <section className="dependencies-table-shell" aria-label="Dependency list">
        {loading ? (
          <div className="dependencies-loading">Loading dependencies...</div>
        ) : filteredDependencies.length === 0 ? (
          <EmptyState>No dependencies match the current filters.</EmptyState>
        ) : (
          <table className="dependencies-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Requested</th>
                <th>Installed</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {filteredDependencies.map((dep) => (
                <tr key={dep.id}>
                  <td className="dependencies-name-cell">
                    <span className="dependencies-ecosystem-icon material-symbols-outlined" aria-hidden="true">
                      {ecosystemIcon(dep.ecosystem)}
                    </span>
                    <span>
                      <strong>{dep.name}</strong>
                      <small>{dep.ecosystem} / {dep.manager}</small>
                    </span>
                  </td>
                  <td className="dependencies-mono">{dep.requested || 'declared'}</td>
                  <td className="dependencies-mono">{dep.installed_version || 'not detected'}</td>
                  <td><CoreUIBadge tone={statusTone(dep.status)}>{dep.status}</CoreUIBadge></td>
                  <td className="dependencies-source-cell">{sourceText(dep)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {job?.steps?.length > 0 ? (
        <section className="dependencies-command-log" aria-label="Dependency command output">
          <h2>Command output</h2>
          {job.steps.map((step) => (
            <details key={`${step.command}:${step.cwd}`} open={!step.ok}>
              <summary>
                <CoreUIBadge tone={step.ok ? 'success' : 'error'}>{step.ok ? 'ok' : 'failed'}</CoreUIBadge>
                <span>{step.command}</span>
                <small>{step.duration_ms} ms</small>
              </summary>
              <pre>{step.output || 'No output'}</pre>
            </details>
          ))}
        </section>
      ) : null}
    </div>
  );
}
