import React from 'react';
import EmptyState from '../EmptyState';
import { t } from '../../services/i18n.js';

export default function RagCollectionsPanel({
  loading,
  collections,
  frameworkSettings,
}) {
  return (
        <div className="rag-collections">
          <div className="collections-header">
            <h3>Collections</h3>
          </div>
          {loading ? (
            <div className="loading">{t('rag.loading_collections')}</div>
          ) : !collections.length ? (
            <EmptyState className="empty-state">{t('rag.empty_collections')}</EmptyState>
          ) : (
            <>
              <table className="collections-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Vectors</th>
                    <th>Segments</th>
                    <th>Shards</th>
                    <th>Replication</th>
                    <th>Vectors Config</th>
                    <th>On Disk</th>
                    <th>Framework</th>
                    <th>Version</th>
                    <th>Last refreshed</th>
                    <th>Type</th>
                    <th>Age vs TTL</th>
                  </tr>
                </thead>
                <tbody>
                  {collections.map((col) => {
                    const isFramework = Boolean(col.framework_id);
                    const isLatest = isFramework && typeof col.name === 'string' && col.name.endsWith('_latest');
                    const ttlDays = frameworkSettings?.framework_latest_ttl_days ?? 90;
                    let ageLabel = '—';
                    if (col.last_refreshed_at && ttlDays && ttlDays > 0) {
                      const refreshed = new Date(col.last_refreshed_at);
                      if (!Number.isNaN(refreshed.getTime())) {
                        const now = new Date();
                        const diffMs = now - refreshed;
                        const ageDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
                        ageLabel = `${ageDays}d / ${ttlDays}d${ageDays > ttlDays ? ' (stale)' : ''}`;
                      }
                    }
                    return (
                      <tr key={col.name}>
                        <td>{col.name}</td>
                        <td>{col.points_count ?? '—'}</td>
                        <td>{col.segments_count ?? '—'}</td>
                        <td>{col.shards_count ?? '—'}</td>
                        <td>{col.replication_factor ?? '—'}</td>
                        <td>
                          {col.vectors_config ? (
                            <div className="vectors-config">
                              <span className="vector-badge">{col.vectors_config.name || 'Default'}</span>
                              <span className="vector-badge">{col.vectors_config.size}</span>
                              <span className="vector-badge">{col.vectors_config.distance || '—'}</span>
                            </div>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td>{col.on_disk ? 'Yes' : 'No'}</td>
                        <td>{col.framework_id || '—'}</td>
                        <td>{col.version || '—'}</td>
                        <td>{col.last_refreshed_at || '—'}</td>
                        <td>{isFramework ? (isLatest ? 'Latest' : 'Archive') : '—'}</td>
                        <td>{isFramework ? ageLabel : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="rag-trigger-hint rag-trigger-hint--offset">
                Collections with a framework id come from external framework docs. Rows marked as
                {' '}
                <strong>Latest</strong>
                {' '}
                (e.g. Alamofire_x.m.n_latest) are refreshed automatically when their age exceeds the configured TTL.
              </p>
            </>
          )}
        </div>
  );
}
