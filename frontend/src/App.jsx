import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { ShieldCheck, Database, LayoutGrid, Sparkles, Layers } from 'lucide-react';
import clsx from 'clsx';

import ReviewPage from './features/review/ReviewPage';
import MemoryBrowser from './features/memory/MemoryBrowser';
import MaintenancePage from './features/maintenance/MaintenancePage';
import TokenAuth from './components/TokenAuth';
import { AUTH_ERROR_EVENT, getNamespaces } from './lib/api';

// ---------------------------------------------------------------------------
// NamespaceSelector — fetches available namespaces and lets the user switch.
// Stores the selection in localStorage so all API requests carry X-Namespace.
// ---------------------------------------------------------------------------
function NamespaceSelector() {
  const [namespaces, setNamespaces] = useState([]);
  const [selected, setSelected] = useState(
    () => localStorage.getItem('selected_namespace') ?? ''
  );

  useEffect(() => {
    getNamespaces()
      .then(setNamespaces)
      .catch(() => setNamespaces([]));
  }, []);

  const handleChange = (e) => {
    const ns = e.target.value;
    setSelected(ns);
    if (ns) {
      localStorage.setItem('selected_namespace', ns);
    } else {
      localStorage.removeItem('selected_namespace');
    }
    // Reload so every page re-fetches data for the new namespace.
    window.location.reload();
  };

  // Only render the selector when multiple namespaces exist (multi-agent setup).
  if (namespaces.length <= 1) return null;

  return (
    <div className="flex items-center gap-2 ml-auto text-sm">
      <Layers size={14} className="text-slate-400 flex-shrink-0" />
      <select
        value={selected}
        onChange={handleChange}
        className="bg-slate-800 border border-slate-700 text-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
        title="Switch agent namespace"
      >
        <option value="">(default)</option>
        {namespaces.filter(ns => ns !== '').map(ns => (
          <option key={ns} value={ns}>{ns}</option>
        ))}
      </select>
    </div>
  );
}

function Layout() {
  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-200">
      {/* Top Navigation Bar */}
      <div className="h-12 border-b border-slate-800 bg-slate-900 flex items-center px-4 gap-6 flex-shrink-0 z-10">
        <div className="font-bold text-slate-100 flex items-center gap-2 mr-4">
          <LayoutGrid className="w-5 h-5 text-indigo-500" />
          <span>Nocturne Admin</span>
        </div>

        <nav className="flex items-center gap-1 h-full">
          <NavLink
            to="/review"
            className={({ isActive }) => clsx(
              "h-full flex items-center gap-2 px-4 text-sm font-medium border-b-2 transition-colors",
              isActive ? "border-indigo-500 text-indigo-400 bg-slate-800/50" : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30"
            )}
          >
            <ShieldCheck size={16} />
            Review & Audit
          </NavLink>

          <NavLink
            to="/memory"
            className={({ isActive }) => clsx(
              "h-full flex items-center gap-2 px-4 text-sm font-medium border-b-2 transition-colors",
              isActive ? "border-emerald-500 text-emerald-400 bg-slate-800/50" : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30"
            )}
          >
            <Database size={16} />
            Memory Explorer
          </NavLink>

          <NavLink
            to="/maintenance"
            className={({ isActive }) => clsx(
              "h-full flex items-center gap-2 px-4 text-sm font-medium border-b-2 transition-colors",
              isActive ? "border-amber-500 text-amber-400 bg-slate-800/50" : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/30"
            )}
          >
            <Sparkles size={16} />
            Brain Cleanup
          </NavLink>
        </nav>

        <NamespaceSelector />
      </div>

      {/* Main Area */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <Routes>
          <Route path="/" element={<Navigate to="/review" replace />} />

          <Route path="/review" element={<ReviewPage />} />

          <Route path="/memory" element={<MemoryBrowser />} />

          <Route path="/maintenance" element={<MaintenancePage />} />
        </Routes>
      </div>
    </div>
  );
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return !!localStorage.getItem('api_token');
  });
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);

  const handleAuthError = useCallback(() => {
    setIsAuthenticated(false);
  }, []);

  const handleAuthenticated = useCallback(() => {
    setIsAuthenticated(true);
  }, []);

  // 组件挂载时，如果当前未认证，尝试发送一个无 token 的请求探测后端是否开启了鉴权
  useEffect(() => {
    let mounted = true;

    const checkAuthStatus = async () => {
      if (isAuthenticated) {
        if (mounted) setIsCheckingAuth(false);
        return;
      }

      try {
        const { getDomains } = await import('./lib/api');
        await getDomains();
        if (mounted) {
          setIsAuthenticated(true);
          setIsCheckingAuth(false);
        }
      } catch (error) {
        if (mounted) {
          setIsCheckingAuth(false);
        }
      }
    };

    checkAuthStatus();

    return () => {
      mounted = false;
    };
  }, [isAuthenticated]);

  // 监听 401 事件，切换回认证界面
  useEffect(() => {
    window.addEventListener(AUTH_ERROR_EVENT, handleAuthError);
    return () => {
      window.removeEventListener(AUTH_ERROR_EVENT, handleAuthError);
    };
  }, [handleAuthError]);

  if (isCheckingAuth) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-slate-950 text-slate-400">
        <div className="w-8 h-8 rounded-full border-2 border-indigo-500/30 border-t-indigo-500 animate-spin mb-4"></div>
        <div className="text-sm">Connecting to Memory Core...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <TokenAuth onAuthenticated={handleAuthenticated} />;
  }

  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  );
}

export default App;
