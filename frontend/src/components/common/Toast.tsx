'use client';

/**
 * MediKiosk in-app notification system (toast) — replaces native browser alert().
 *
 * Design constraints (Phase 10):
 *  - Matches the existing light-purple design system (#6C3FC5 / #4B238C / #F3EEFC,
 *    rounded-xl white cards, neutral-200 borders, #171717 / #666666 text). No new
 *    visual theme and no new dependencies (lucide-react icons only).
 *  - Non-blocking, accessible (aria-live polite/assertive), dismissible, responsive.
 *  - Critical variants (error/warning) linger longer and are assertive; routine
 *    success/info auto-dismiss quickly. duration = 0 keeps a toast until dismissed.
 *  - De-duplicates identical messages so a flaky action cannot stack toasts, and
 *    never renders caller-supplied identifiers beyond a plain message string
 *    (callers must not pass patient data).
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';

export type ToastVariant = 'success' | 'error' | 'info' | 'warning';

export interface ToastOptions {
  /** Optional bold headline. Keep it short and professional. */
  title?: string;
  /** Optional supporting line. Do NOT include patient names / IDs / PHI. */
  description?: string;
  /** Visible time in ms. 0 = sticky until dismissed. Defaults per variant. */
  duration?: number;
}

interface ToastItem {
  id: number;
  variant: ToastVariant;
  title?: string;
  description?: string;
  duration: number;
}

interface ToastApi {
  show: (variant: ToastVariant, message: string, options?: ToastOptions) => void;
  success: (message: string, options?: ToastOptions) => void;
  error: (message: string, options?: ToastOptions) => void;
  info: (message: string, options?: ToastOptions) => void;
  warning: (message: string, options?: ToastOptions) => void;
  dismiss: (id: number) => void;
}

// Sensible per-variant auto-dismiss timings (ms). Critical feedback must not
// vanish too quickly; errors are the slowest.
const DEFAULT_DURATION: Record<ToastVariant, number> = {
  success: 4000,
  info: 4500,
  warning: 7000,
  error: 9000,
};

const TOAST_STYLE: Record<
  ToastVariant,
  { Icon: typeof CheckCircle2; iconWrap: string; accent: string }
> = {
  success: { Icon: CheckCircle2, iconWrap: 'bg-emerald-50 text-emerald-600', accent: 'border-l-emerald-500' },
  error: { Icon: AlertCircle, iconWrap: 'bg-red-50 text-red-600', accent: 'border-l-red-500' },
  warning: { Icon: AlertTriangle, iconWrap: 'bg-amber-50 text-amber-600', accent: 'border-l-amber-500' },
  info: { Icon: Info, iconWrap: 'bg-[#F3EEFC] text-[#6C3FC5]', accent: 'border-l-[#6C3FC5]' },
};

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  // Track timers so unmount / dismiss can clear pending auto-dismiss timeouts.
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const show = useCallback(
    (variant: ToastVariant, message: string, options: ToastOptions = {}) => {
      const title = options.title;
      const description = options.description;
      const duration = options.duration ?? DEFAULT_DURATION[variant];

      setToasts((prev) => {
        // De-duplicate: skip if an identical visible toast already exists.
        const isDuplicate = prev.some(
          (t) =>
            t.variant === variant &&
            t.title === title &&
            t.description === description &&
            (t as ToastItem & { _message?: string })._message === message
        );
        if (isDuplicate) return prev;

        const id = ++idRef.current;
        const item: ToastItem & { _message?: string } = {
          id,
          variant,
          title,
          description,
          duration,
          _message: message,
        };
        // Keep the stack bounded (max 4) — newest wins.
        const next = [...prev, item].slice(-4);
        if (duration > 0) {
          const timer = setTimeout(() => dismiss(id), duration);
          timersRef.current.set(id, timer);
        }
        return next;
      });
    },
    [dismiss]
  );

  const api = useMemo<ToastApi>(
    () => ({
      show,
      success: (m, o) => show('success', m, o),
      error: (m, o) => show('error', m, o),
      info: (m, o) => show('info', m, o),
      warning: (m, o) => show('warning', m, o),
      dismiss,
    }),
    [show, dismiss]
  );

  // Clean up any outstanding timers on unmount.
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        role="region"
        aria-label="Notifications"
        className="fixed top-4 right-4 z-[120] flex flex-col gap-2.5 w-[calc(100vw-2rem)] max-w-sm pointer-events-none"
      >
        {toasts.map((t) => {
          const { Icon, iconWrap, accent } = TOAST_STYLE[t.variant];
          // error / warning are assertive (immediately announced); others polite.
          const ariaRole = t.variant === 'error' || t.variant === 'warning' ? 'alert' : 'status';
          return (
            <div
              key={t.id}
              role={ariaRole}
              className={`mk-toast-in pointer-events-auto flex items-start gap-3 bg-white rounded-xl border border-neutral-200 ${accent} border-l-4 shadow-xl p-3.5`}
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${iconWrap}`}>
                <Icon className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-[#171717] leading-snug break-words">{t.title || defaultMessage(t)}</p>
                {t.description && (
                  <p className="mt-0.5 text-xs text-[#666666] leading-relaxed break-words">{t.description}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss notification"
                className="text-[#666666] hover:text-[#171717] p-0.5 rounded-md -mr-1 -mt-1 flex-shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

/** Fall back to the plain message when no explicit title was supplied. */
function defaultMessage(t: ToastItem & { _message?: string }): string {
  return t._message || t.title || '';
}

/** Access the toast API from any client component. */
export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Fail soft: a missing provider should not crash clinical workflows.
    const noop: ToastApi = {
      show: () => {},
      success: () => {},
      error: () => {},
      info: () => {},
      warning: () => {},
      dismiss: () => {},
    };
    if (typeof process !== 'undefined' && process.env.NODE_ENV !== 'production') {
      console.warn('useToast() used outside <ToastProvider>. Notifications are disabled.');
    }
    return noop;
  }
  return ctx;
}
