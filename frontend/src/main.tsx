import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
import { applyTheme } from './pages/settings/PreferencesTab';

try {
  const raw = localStorage.getItem('rooman_account_preferences');
  if (raw) {
    const prefs = JSON.parse(raw);
    if (prefs.theme) {
      applyTheme(prefs.theme);
    }
  }
} catch {
  // Ignore localStorage parsing errors
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

