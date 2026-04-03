import React, {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import './Tabs.css';

const MENU_BUTTON_WIDTH = 44;

function parseGapPx(cssValue) {
  const n = parseFloat(cssValue);
  return Number.isFinite(n) ? n : 0;
}

/**
 * @param {number[]} widths
 * @param {number} barWidth
 * @param {number} tabGap column-gap between tab buttons
 * @param {number} barFlexGap gap between visible strip and menu button on .tabs-bar
 * @param {number} menuWidth
 * @returns {number} index of first tab in overflow; tabs.length if none
 */
function computeFirstOverflowIndex(widths, barWidth, tabGap, barFlexGap, menuWidth) {
  const n = widths.length;
  if (n === 0) {
    return 0;
  }
  const sumTabs =
    widths.reduce((acc, w) => acc + w, 0) + Math.max(0, n - 1) * tabGap;
  if (sumTabs <= barWidth) {
    return n;
  }
  const available = barWidth - menuWidth - barFlexGap;
  let used = 0;
  let count = 0;
  for (let i = 0; i < n; i++) {
    const w = widths[i];
    const step = count === 0 ? w : w + tabGap;
    if (used + step <= available) {
      used += step;
      count++;
    } else {
      break;
    }
  }
  if (count < 1) {
    count = 1;
  }
  return count;
}

function TabBarButton({ tab, activeTab, tabErrors, onClick, tabIndex }) {
  const hasError = Boolean(tabErrors && tabErrors[tab.id]);
  return (
    <button
      type="button"
      className={`tab ${activeTab === tab.id ? 'active' : ''}`}
      onClick={onClick}
      tabIndex={tabIndex}
    >
      <span className="tab-label">{tab.label}</span>
      {hasError && (
        <span className="tab-error-badge" aria-label="Tab has configuration errors">
          !
        </span>
      )}
    </button>
  );
}

function TabsOverflowIcon() {
  return (
    <svg
      className="tabs-overflow-trigger-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function Tabs({ tabs, activeTab, onTabChange, tabErrors }) {
  const menuId = useId();
  const [overflowStartIndex, setOverflowStartIndex] = useState(() => tabs.length);
  const [menuOpen, setMenuOpen] = useState(false);

  const measureRowRef = useRef(null);
  const barRef = useRef(null);
  const menuWrapRef = useRef(null);

  const tabsSignature = tabs.map((t) => `${t.id}:${t.label}`).join('|');

  const updateOverflow = useCallback(() => {
    const bar = barRef.current;
    const measureRow = measureRowRef.current;
    if (!bar || !measureRow) {
      return;
    }
    const buttons = measureRow.querySelectorAll('button.tab');
    if (buttons.length !== tabs.length) {
      return;
    }
    const widths = Array.from(buttons).map((el) => el.getBoundingClientRect().width);
    const barWidth = bar.getBoundingClientRect().width;
    const tabGap = parseGapPx(getComputedStyle(measureRow).columnGap);
    const barFlexGap = parseGapPx(getComputedStyle(bar).columnGap);
    const next = computeFirstOverflowIndex(
      widths,
      barWidth,
      tabGap,
      barFlexGap,
      MENU_BUTTON_WIDTH,
    );
    setOverflowStartIndex(next);
  }, [tabs.length, tabsSignature]);

  useLayoutEffect(() => {
    updateOverflow();
  }, [updateOverflow, tabsSignature, tabErrors, activeTab]);

  useEffect(() => {
    const bar = barRef.current;
    if (!bar || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const ro = new ResizeObserver(() => {
      updateOverflow();
    });
    ro.observe(bar);
    return () => ro.disconnect();
  }, [updateOverflow]);

  useEffect(() => {
    if (overflowStartIndex >= tabs.length) {
      setMenuOpen(false);
    }
  }, [overflowStartIndex, tabs.length]);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }
    const onDocMouseDown = (e) => {
      const wrap = menuWrapRef.current;
      if (wrap && !wrap.contains(e.target)) {
        setMenuOpen(false);
      }
    };
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocMouseDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [menuOpen]);

  const visibleTabs = tabs.slice(0, overflowStartIndex);
  const overflowTabs = tabs.slice(overflowStartIndex);
  const activeInOverflow = overflowTabs.some((t) => t.id === activeTab);

  return (
    <div className="tabs-container">
      <div className="tabs-inner">
        <div className="tabs-measure-row" ref={measureRowRef} aria-hidden="true">
          {tabs.map((tab) => (
            <TabBarButton
              key={`m-${tab.id}`}
              tab={tab}
              activeTab={activeTab}
              tabErrors={tabErrors}
              onClick={() => {}}
              tabIndex={-1}
            />
          ))}
        </div>
        <div className="tabs-bar" ref={barRef}>
          <div className="tabs-visible">
            {visibleTabs.map((tab) => (
              <TabBarButton
                key={tab.id}
                tab={tab}
                activeTab={activeTab}
                tabErrors={tabErrors}
                onClick={() => onTabChange(tab.id)}
              />
            ))}
          </div>
          {overflowTabs.length > 0 && (
            <div className="tabs-overflow-wrap" ref={menuWrapRef}>
              <button
                type="button"
                className={`tabs-overflow-trigger${activeInOverflow ? ' tabs-overflow-trigger--active-context' : ''}`}
                aria-label="More tabs"
                aria-expanded={menuOpen}
                aria-controls={menuId}
                aria-haspopup="menu"
                onClick={() => setMenuOpen((o) => !o)}
              >
                <TabsOverflowIcon />
              </button>
              {menuOpen && (
                <div className="tabs-overflow-menu" id={menuId} role="menu">
                  {overflowTabs.map((tab) => {
                    const hasError = Boolean(tabErrors && tabErrors[tab.id]);
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        role="menuitem"
                        className={`tabs-overflow-menu-item${activeTab === tab.id ? ' active' : ''}`}
                        onClick={() => {
                          onTabChange(tab.id);
                          setMenuOpen(false);
                        }}
                      >
                        <span className="tab-label">{tab.label}</span>
                        {hasError && (
                          <span
                            className="tab-error-badge"
                            aria-label="Tab has configuration errors"
                          >
                            !
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Tabs;
