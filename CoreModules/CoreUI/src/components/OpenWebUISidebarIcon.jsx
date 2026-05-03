import openWebUiIconRaw from '../../../../extensions/bundled/open-webui/icons/open-webui-light.svg?raw';

export default function OpenWebUISidebarIcon() {
  return (
    <span
      className="coreui-sidebar__icon coreui-sidebar__icon--svg"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: openWebUiIconRaw }}
    />
  );
}
