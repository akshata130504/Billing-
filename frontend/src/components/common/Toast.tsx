import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { cn } from '../../utils/cn';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastContextValue {
  showToast: (type: ToastType, title: string, message?: string, duration?: number) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  // Pending auto-dismiss timers, cleared on unmount so none fires after the provider is gone.
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach(clearTimeout);
      pending.clear();
    };
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (type: ToastType, title: string, message?: string, duration = 4000) => {
      const id = Math.random().toString(36).substring(2, 9);
      const newToast: ToastMessage = { id, type, title, message, duration };
      setToasts((prev) => [...prev, newToast]);

      if (duration > 0) {
        const timer = setTimeout(() => {
          timers.current.delete(timer);
          removeToast(id);
        }, duration);
        timers.current.add(timer);
      }
    },
    [removeToast]
  );

  const icons = {
    success: <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />,
    error: <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />,
    warning: <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />,
    info: <Info className="w-5 h-5 text-blue-600 shrink-0" />,
  };

  const borders = {
    success: 'border-emerald-200 bg-white shadow-elevated',
    error: 'border-rose-200 bg-white shadow-elevated',
    warning: 'border-amber-200 bg-white shadow-elevated',
    info: 'border-blue-200 bg-white shadow-elevated',
  };

  return (
    <ToastContext.Provider value={{ showToast, removeToast }}>
      {children}
      {/* Floating toast stack */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="alert"
            className={cn(
              'pointer-events-auto flex items-start p-3.5 rounded-xl border transition-all transform animate-toast-in',
              borders[toast.type]
            )}
          >
            <div className="mr-3 mt-0.5">{icons[toast.type]}</div>
            <div className="flex-1 min-w-0 mr-2">
              <h4 className="text-xs font-semibold text-slate-900">{toast.title}</h4>
              {toast.message && (
                <p className="mt-0.5 text-xs text-slate-600 leading-relaxed">
                  {toast.message}
                </p>
              )}
            </div>
            <button
              onClick={() => removeToast(toast.id)}
              className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              aria-label="Dismiss toast"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
