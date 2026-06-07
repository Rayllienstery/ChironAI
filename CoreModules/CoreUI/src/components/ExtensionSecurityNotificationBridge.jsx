import { useEffect, useMemo, useRef, useState } from 'react';
import { getExtensionInstalled } from '../services/api';
import { useNotificationCenter } from './NotificationCenterContext';

const POLL_MS = 15000;

function findingFingerprint(finding) {
  return [
    finding?.code || 'unknown',
    finding?.file || '',
    finding?.line || '',
    finding?.evidence || finding?.message || '',
  ].join('|');
}

function extensionFingerprint(item) {
  const findings = Array.isArray(item?.security_findings) ? item.security_findings : [];
  const raw = findings.map(findingFingerprint).sort().join('||') || String(item?.error || '');
  let hash = 0;
  for (let i = 0; i < raw.length; i += 1) {
    hash = ((hash << 5) - hash + raw.charCodeAt(i)) | 0;
  }
  return Math.abs(hash).toString(36);
}

function blockedExtensions(items) {
  return (Array.isArray(items) ? items : []).filter((item) => {
    if (!item) return false;
    if (item.security_blocked) return true;
    const findings = Array.isArray(item.security_findings) ? item.security_findings : [];
    return findings.some((finding) => finding?.severity === 'critical');
  });
}

function sandboxFailedExtensions(items) {
  return (Array.isArray(items) ? items : []).filter((item) => {
    const status = String(item?.sandbox_status || '').toLowerCase();
    return Boolean(item?.sandbox_error || item?.sandbox_last_error || item?.sandbox_blocked)
      || ['blocked', 'crashed', 'timeout', 'protocol_error', 'error'].includes(status);
  });
}

function notificationMessage(item) {
  const findings = Array.isArray(item?.security_findings) ? item.security_findings : [];
  const first = findings.find((finding) => finding?.severity === 'critical') || findings[0];
  const title = item?.title || item?.id || 'Extension';
  const detail = first?.message || item?.error || 'Unsafe extension code was blocked before it could load.';
  const location = first?.file ? ` (${first.file}${first.line ? `:${first.line}` : ''})` : '';
  return `${title}: ${detail}${location}`;
}

/**
 * Polls the extension security/permissions service and surfaces blocked events
 * to the notification center.
 */
export default function ExtensionSecurityNotificationBridge() {
  const {
    sessionId,
    persisted,
    persistedLoaded,
    persistNotification,
  } = useNotificationCenter();
  const [blocked, setBlocked] = useState([]);
  const [sandboxFailed, setSandboxFailed] = useState([]);
  const notifiedRef = useRef(new Set());

  useEffect(() => {
    if (!sessionId) return undefined;
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getExtensionInstalled({ dockerVersions: false });
        if (!cancelled) {
          const extensions = data?.extensions || [];
          setBlocked(blockedExtensions(extensions));
          setSandboxFailed(sandboxFailedExtensions(extensions));
        }
      } catch {
        if (!cancelled) {
          setBlocked([]);
          setSandboxFailed([]);
        }
      }
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [sessionId]);

  const existingKeys = useMemo(() => {
    return new Set(
      (Array.isArray(persisted) ? persisted : [])
        .map((item) => item?.aggregation_key)
        .filter(Boolean),
    );
  }, [persisted]);

  useEffect(() => {
    if (!sessionId || !persistedLoaded || !persistNotification) return;
    blocked.forEach((item) => {
      const extId = String(item?.id || '').trim();
      if (!extId) return;
      const aggregationKey = `extensions-security:${extId}:${extensionFingerprint(item)}`;
      if (existingKeys.has(aggregationKey) || notifiedRef.current.has(aggregationKey)) return;
      notifiedRef.current.add(aggregationKey);
      void persistNotification({
        kind: 'error',
        source: 'extensions',
        title: 'Extension blocked by security scan',
        message: notificationMessage(item).slice(0, 800),
        metadata: {
          extension_id: extId,
          security_findings: Array.isArray(item.security_findings) ? item.security_findings : [],
        },
        aggregation_key: aggregationKey,
      });
    });
  }, [blocked, existingKeys, persistedLoaded, persistNotification, sessionId]);

  useEffect(() => {
    if (!sessionId || !persistedLoaded || !persistNotification) return;
    sandboxFailed.forEach((item) => {
      const extId = String(item?.id || '').trim();
      if (!extId) return;
      const raw = `${item?.sandbox_status || 'error'}:${item?.sandbox_last_error || item?.sandbox_error || item?.error || ''}`;
      let hash = 0;
      for (let i = 0; i < raw.length; i += 1) {
        hash = ((hash << 5) - hash + raw.charCodeAt(i)) | 0;
      }
      const aggregationKey = `extensions-sandbox:${extId}:${Math.abs(hash).toString(36)}`;
      if (existingKeys.has(aggregationKey) || notifiedRef.current.has(aggregationKey)) return;
      notifiedRef.current.add(aggregationKey);
      void persistNotification({
        kind: 'error',
        source: 'extensions',
        title: 'Extension sandbox failed',
        message: `${item?.title || extId}: ${item?.sandbox_last_error || item?.sandbox_error || item?.error || 'Sandbox worker failed.'}`.slice(0, 800),
        metadata: {
          extension_id: extId,
          sandbox_status: item?.sandbox_status || '',
        },
        aggregation_key: aggregationKey,
      });
    });
  }, [existingKeys, persistedLoaded, persistNotification, sandboxFailed, sessionId]);

  return null;
}
