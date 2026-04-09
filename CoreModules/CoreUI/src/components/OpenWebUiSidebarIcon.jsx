import openWebUiIconRaw from '../assets/openwebui-icon.svg?raw';

export default function OpenWebUiSidebarIcon() {
  return (
    <span
      className="coreui-sidebar__icon coreui-sidebar__icon--openwebui"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: openWebUiIconRaw }}
    />
  );
}
