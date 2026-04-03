import React from 'react';
import './Tabs.css';

function Tabs({ tabs, activeTab, onTabChange, tabErrors }) {
  return (
    <div className="tabs-container">
      <div className="tabs">
        {tabs.map((tab) => {
          const hasError = Boolean(tabErrors && tabErrors[tab.id]);
          return (
            <button
              key={tab.id}
              className={`tab ${activeTab === tab.id ? 'active' : ''}`}
              type="button"
              onClick={() => onTabChange(tab.id)}
            >
              <span className="tab-label">{tab.label}</span>
              {hasError && (
                <span className="tab-error-badge" aria-label="Tab has configuration errors">
                  !
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default Tabs;

