import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import HelpPanel from './HelpPanel.jsx';
import { parseHelpRef } from '../../utils/helpRef.js';

const HelpPanelContext = createContext(null);

/**
 * @typedef {Object} HelpPanelApi
 * @property {(helpRef: string, label?: string) => void} openHelp
 * @property {() => void} closeHelp
 */

/**
 * @param {Object} props
 * @param {React.ReactNode} props.children
 * @param {(slug: string, anchor?: string) => void} [props.onOpenFullHelp]
 */
export function HelpPanelProvider({ children, onOpenFullHelp }) {
  const [panel, setPanel] = useState({
    open: false,
    slug: '',
    anchor: '',
    label: '',
  });

  const openHelp = useCallback((helpRef, label = '') => {
    const { slug, anchor } = parseHelpRef(helpRef);
    if (!slug) return;
    setPanel({ open: true, slug, anchor, label: String(label || '') });
  }, []);

  const closeHelp = useCallback(() => {
    setPanel((prev) => ({ ...prev, open: false }));
  }, []);

  const value = useMemo(() => ({ openHelp, closeHelp }), [openHelp, closeHelp]);

  return (
    <HelpPanelContext.Provider value={value}>
      {children}
      <HelpPanel
        open={panel.open}
        slug={panel.slug}
        anchor={panel.anchor}
        label={panel.label}
        onClose={closeHelp}
        onOpenFullHelp={onOpenFullHelp}
      />
    </HelpPanelContext.Provider>
  );
}

/** @returns {HelpPanelApi} */
export function useHelpPanel() {
  const ctx = useContext(HelpPanelContext);
  if (!ctx) {
    throw new Error('useHelpPanel must be used within HelpPanelProvider');
  }
  return ctx;
}
