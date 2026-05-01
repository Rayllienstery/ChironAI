import ollamaIconRaw from '../assets/ollama-icon.svg?raw';

export default function OllamaSidebarIcon() {
  return (
    <span
      className="coreui-sidebar__icon coreui-sidebar__icon--ollama"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ollamaIconRaw }}
    />
  );
}
