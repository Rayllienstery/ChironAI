import StandByScreen from './StandByScreen.jsx';
import '../styles/components/StandByScreen.css';

export default {
  title: 'CoreUI/StandByScreen',
};

export function Default() {
  return (
    <StandByScreen
      moduleName="RAG"
      message="Stand by..."
      submessage="Loading collections"
    />
  );
}

export function Large() {
  return (
    <StandByScreen
      size="lg"
      moduleName="Extensions"
      message="Preparing extension host"
      submessage="This may take a moment"
    />
  );
}
