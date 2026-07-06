import { useEffect, useRef } from 'react';
import { useNotificationCenter } from './NotificationCenterContext';
import { getVersion } from '../services/api';

const WELCOME_NOTIF_STORAGE_KEY = 'chironai_welcome_notif_version';

/**
 * Side-effect-only bridge: shows a one-time welcome notification in the
 * notification center when the user opens the WebUI for a new version.
 */
export default function WelcomeNotificationBridge() {
  const { persistNotification } = useNotificationCenter();
  const hasCheckedRef = useRef(false);

  useEffect(() => {
    if (hasCheckedRef.current || !persistNotification) return;
    hasCheckedRef.current = true;

    const checkVersionAndNotify = async () => {
      try {
        const data = await getVersion();
        if (!data || !data.version) return;

        const lastShownVersion = localStorage.getItem(WELCOME_NOTIF_STORAGE_KEY);
        if (lastShownVersion === data.version) return;

        // Show notification
        const lines = (data.changelog || '').split('\n');
        const formatted = lines
          .map((line, i) => {
            const isHeader = /^###\s+/.test(line);
            if (!isHeader) return line;
            const label = line.replace(/^###\s+/, '');
            return (i > 0 ? '\n' : '') + '● ' + label;
          })
          .filter(Boolean)
          .join('\n');

        await persistNotification({
          title: data.display_name || `${data.app_name || 'Chiron AI'} ${data.version}`.trim(),
          message: formatted || 'New version is here!',
          tone: 'info',
          source: 'system',
          sticky: true,
        });

        localStorage.setItem(WELCOME_NOTIF_STORAGE_KEY, data.version);
      } catch (error) {
        console.error('WelcomeNotificationBridge: failed to check version', error);
      }
    };

    void checkVersionAndNotify();
  }, [persistNotification]);

  return null;
}
