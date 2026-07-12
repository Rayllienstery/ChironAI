import { useCallback, useState } from 'react';
import { getProxyLogs } from '../services/api';
import {
  clearRemoteRevealPin,
  getRemoteRevealPin,
  needsRemoteRevealPin,
  setRemoteRevealPin,
} from '../services/remoteRevealPin';
import CoreUIButton from './CoreUIButton';

/**
 * On LAN, require the reveal PIN before rendering log/proxy observability UI.
 * PIN is kept in memory only (same session PIN as remote API key reveal).
 */
export default function RemoteRevealPinGate({ children }) {
  const [pinInput, setPinInput] = useState('');
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [unlocked, setUnlocked] = useState(
    () => !needsRemoteRevealPin() || Boolean(getRemoteRevealPin()),
  );

  const handleUnlock = useCallback(async () => {
    setErr(null);
    setBusy(true);
    const pin = pinInput.trim();
    if (pin.length < 4) {
      setErr('Enter your 4–8 digit reveal PIN.');
      setBusy(false);
      return;
    }
    setRemoteRevealPin(pin);
    try {
      await getProxyLogs({ limit: 1 });
      setUnlocked(true);
    } catch (e) {
      clearRemoteRevealPin();
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }, [pinInput]);

  if (!needsRemoteRevealPin() || unlocked) {
    return children;
  }

  return (
    <section className="app-default-card remote-reveal-pin-gate" aria-labelledby="remote-reveal-pin-gate-heading">
      <h2 id="remote-reveal-pin-gate-heading">Remote reveal PIN required</h2>
      <p className="dashboard-card-muted">
        Logs and proxy traces from this device require the same PIN used to reveal the API key remotely.
        Install the PIN on the host at <code>http://127.0.0.1:&lt;port&gt;/webui</code> (Tokens and Security → Remote Access).
      </p>
      <label htmlFor="remote-reveal-pin-gate-input">Reveal PIN</label>
      <input
        id="remote-reveal-pin-gate-input"
        type="password"
        inputMode="numeric"
        pattern="\d{4,8}"
        maxLength={8}
        value={pinInput}
        onChange={(e) => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 8))}
        placeholder="4–8 digit PIN"
        autoComplete="off"
      />
      {err && <div className="dashboard-card-error">{err}</div>}
      <div className="dashboard-card-actions">
        <CoreUIButton variant="primary" onClick={handleUnlock} disabled={busy || pinInput.length < 4}>
          Unlock logs
        </CoreUIButton>
      </div>
    </section>
  );
}
