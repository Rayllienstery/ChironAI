import { useEffect, useState } from 'react';
import { getVersion } from '../services/api';
import { t } from '../services/i18n.js';
import Card from './Card';
import ChironaiLogo from './ChironaiLogo';
import '../styles/components/AboutTab.css';

const GITHUB_URL = 'https://github.com/Rayllienstery/ChironAI';
const LINKEDIN_URL = 'https://www.linkedin.com/in/kostiantyn-kolosov/';

function AboutTab({ appVersion: appVersionProp = null }) {
  const [versionInfo, setVersionInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getVersion();
        if (!cancelled) {
          setVersionInfo(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const version = versionInfo?.version || appVersionProp || t('about.version_unknown');
  const stage = versionInfo?.stage || '';
  const displayName = t('app.title');
  const appName = versionInfo?.app_name || 'chironai';

  return (
    <div className="about-tab tab-view">
      <section className="about-hero" aria-label={t('about.project_aria')}>
        <div className="about-logo-wrap">
          <img
            src="/favicon-512.png"
            alt={t('about.logo_alt')}
            className="about-logo"
            width="512"
            height="512"
            onError={(e) => {
              e.currentTarget.style.display = 'none';
            }}
          />
          <div className="about-logo-fallback" aria-hidden="true">
            <ChironaiLogo size={192} />
          </div>
        </div>
        <div className="about-hero-copy">
          <h1 className="about-app-name">{displayName}</h1>
          <div className="about-version-row">
            <span className="about-version-badge" title={t('about.version_title')}>
              {t('about.version_label')} {version}
            </span>
            {stage && (
              <span className="about-stage-badge" title={t('about.stage_title')}>
                {stage}
              </span>
            )}
          </div>
          {loading && <p className="about-version-hint">{t('about.loading_version')}</p>}
          {error && !versionInfo && !appVersionProp && (
            <p className="about-version-error">{t('about.version_error')}</p>
          )}
        </div>
      </section>

      <div className="about-grid">
        <Card className="about-card about-card--description">
          <h3>{t('about.what_is_title')}</h3>
          <p>{t('app.subtitle')}</p>
          <p>{t('about.description')}</p>
        </Card>

        <Card className="about-card about-card--links">
          <h3>{t('about.links_title')}</h3>
          <ul className="about-link-list">
            <li>
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="about-link about-link--github"
                aria-label={t('about.github_aria')}
              >
                <span className="about-link__icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="20" height="20">
                    <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
                  </svg>
                </span>
                <span className="about-link__text">{t('about.github_label')}</span>
              </a>
            </li>
            <li>
              <a
                href={LINKEDIN_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="about-link about-link--linkedin"
                aria-label={t('about.linkedin_aria')}
              >
                <span className="about-link__icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="20" height="20">
                    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
                  </svg>
                </span>
                <span className="about-link__text">{t('about.linkedin_label')}</span>
              </a>
            </li>
          </ul>
        </Card>

        <Card className="about-card about-card--credits">
          <h3>{t('about.credits_title')}</h3>
          <p>{t('about.credits_intro')}</p>
          <ul className="about-credit-list">
            <li>{t('about.credit.react')}</li>
            <li>{t('about.credit.vite')}</li>
            <li>{t('about.credit.material_symbols')}</li>
            <li>{t('about.credit.qdrant')}</li>
            <li>{t('about.credit.docker')}</li>
            <li>{t('about.credit.ollama')}</li>
          </ul>
        </Card>

        <Card className="about-card about-card--license">
          <h3>{t('about.license_title')}</h3>
          <p>{t('about.license_text')}</p>
          <p className="about-license-note">{t('about.license_note')}</p>
        </Card>
      </div>
    </div>
  );
}

export default AboutTab;
