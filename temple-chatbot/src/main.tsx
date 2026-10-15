import React from 'react';
import ReactDOM from 'react-dom/client';
import DemoApp from '../demo/DemoApp';

const rootElement = document.getElementById('root');
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <DemoApp />
    </React.StrictMode>
  );
}
