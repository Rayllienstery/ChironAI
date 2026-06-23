import { useState } from 'react';
import CoreUIPillTabs from '../CoreUIPillTabs';
import { SHOWCASE_SUBTABS } from './CoreUIShowcasePrimitives';
import ColorsShowcase from './ColorsShowcase';
import ButtonsShowcase from './ButtonsShowcase';
import CardsShowcase from './CardsShowcase';
import ComponentsShowcase from './ComponentsShowcase';
import LayoutShowcase from './LayoutShowcase';
import DataShowcase from './DataShowcase';
import IconsShowcase from './IconsShowcase';
import NotificationsShowcase from './NotificationsShowcase';
import '../../styles/components/DockerTab.css';
import '../../styles/components/DependenciesTab.css';
import '../../styles/components/CoreUIShowcaseTab.css';

export default function CoreUIShowcaseTab() {
  const [subtab, setSubtab] = useState('colors');

  return (
    <div className="coreui-showcase tab-view">
      <header className="coreui-showcase-hero">
        <div>
          <span className="coreui-showcase-kicker">Design system inventory</span>
          <h1>CoreUI Showcase</h1>
        </div>
        <p>
          Static catalog of reusable CoreUI primitives and common visual patterns.
        </p>
      </header>

      <CoreUIPillTabs
        tabs={[...SHOWCASE_SUBTABS]}
        value={subtab}
        onChange={(id: string) => setSubtab(id)}
        ariaLabel="Showcase categories"
      />

      {subtab === 'colors' && <ColorsShowcase />}
      {subtab === 'buttons' && <ButtonsShowcase />}
      {subtab === 'cards' && <CardsShowcase />}
      {subtab === 'components' && <ComponentsShowcase />}
      {subtab === 'layout' && <LayoutShowcase />}
      {subtab === 'data' && <DataShowcase />}
      {subtab === 'icons' && <IconsShowcase />}
      {subtab === 'notifications' && <NotificationsShowcase />}
    </div>
  );
}
