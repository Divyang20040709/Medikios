'use client';

/**
 * MediKiosk NotificationModal — an accessible in-app dialog that replaces native
 * window.alert() / window.confirm() for messages and decisions that must be
 * acknowledged (emergency assistance, clinical red flags, destructive actions).
 *
 * Behaviour:
 *  - role="dialog" aria-modal, labelled by its title, described by its body.
 *  - Focus moves into the dialog on open and is trapped with Tab / Shift+Tab.
 *  - Escape triggers the cancel path (or acknowledge when there is no cancel).
 *  - Focus is restored to the previously focused element on close.
 *  - Tone colours match the light-purple design system (no new theme).
 *
 * The modal renders exactly the copy the caller supplies — callers are
 * responsible for not putting patient data into title/description.
 */

import React, { useEffect, useRef, useCallback } from 'react';
import { AlertTriangle, CheckCircle2, PhoneCall, Info } from 'lucide-react';

export type ModalTone = 'info' | 'success' | 'warning' | 'danger' | 'emergency';

export interface NotificationModalProps {
  open: boolean;
  /** Headline (required). Keep it short and professional. */
  title: string;
  /** Supporting text describing what happened / what is needed. */
  description?: string;
  tone?: ModalTone;
  /** Dismiss / secondary action. Always available (also fired by Escape). */
  onCancel?: () => void;
  /** Primary decision action. When provided the dialog renders Cancel + Confirm. */
  onConfirm?: () => void;
  /** Confirm/primary action label. Defaults to the acknowledge label. */
  confirmLabel?: string;
  /** Cancel/secondary action label (only shown when onCancel is provided). */
  cancelLabel?: string;
  /** Label for a purely informational acknowledge button. */
  acknowledgeLabel?: string;
  /** If true, clicking the backdrop does not close the dialog. */
  disableBackdropClose?: boolean;
}

const TONE_CONFIG: Record<
  ModalTone,
  { Icon: typeof Info; iconWrap: string; primaryBtn: string }
> = {
  info: {
    Icon: Info,
    iconWrap: 'bg-[#F3EEFC] text-[#6C3FC5]',
    primaryBtn: 'bg-[#6C3FC5] hover:bg-[#4B238C] text-white',
  },
  success: {
    Icon: CheckCircle2,
    iconWrap: 'bg-emerald-50 text-emerald-600 border border-emerald-200',
    primaryBtn: 'bg-emerald-600 hover:bg-emerald-700 text-white',
  },
  warning: {
    Icon: AlertTriangle,
    iconWrap: 'bg-amber-50 text-amber-600 border border-amber-200',
    primaryBtn: 'bg-amber-600 hover:bg-amber-700 text-white',
  },
  danger: {
    Icon: AlertTriangle,
    iconWrap: 'bg-red-50 text-red-600 border border-red-200',
    primaryBtn: 'bg-red-600 hover:bg-red-700 text-white',
  },
  emergency: {
    Icon: PhoneCall,
    iconWrap: 'bg-red-50 text-red-600 border border-red-200',
    primaryBtn: 'bg-[#4B238C] hover:bg-[#6C3FC5] text-white',
  },
};

export function NotificationModal({
  open,
  title,
  description,
  tone = 'info',
  onCancel,
  onConfirm,
  confirmLabel,
  cancelLabel = 'Cancel',
  acknowledgeLabel = 'OK',
  disableBackdropClose = false,
}: NotificationModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);
  const lastFocused = useRef<HTMLElement | null>(null);

  // A dialog is a decision (two buttons) only when a confirm handler is given;
  // otherwise it is a single acknowledge-only alert.
  const hasConfirm = typeof onConfirm === 'function';

  const dismiss = useCallback(() => {
    onCancel?.();
  }, [onCancel]);

  const primaryAction = useCallback(() => {
    if (hasConfirm && onConfirm) {
      onConfirm();
    } else {
      dismiss();
    }
  }, [hasConfirm, onConfirm, dismiss]);

  // Focus management: capture the trigger, move focus into the dialog on open,
  // restore on close.
  useEffect(() => {
    if (!open) return;
    lastFocused.current = document.activeElement as HTMLElement | null;
    const id = window.setTimeout(() => primaryRef.current?.focus(), 20);
    return () => {
      window.clearTimeout(id);
      lastFocused.current?.focus?.();
    };
  }, [open]);

  // Keyboard: Escape dismisses; Tab is trapped within the dialog.
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        if (!disableBackdropClose) dismiss();
        return;
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [dismiss, disableBackdropClose]
  );

  if (!open) return null;

  const { Icon, iconWrap, primaryBtn } = TONE_CONFIG[tone];

  return (
    <div
      className="fixed inset-0 z-[110] bg-black/50 flex items-center justify-center p-4"
      onClick={() => {
        if (!disableBackdropClose) dismiss();
      }}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="mk-modal-title"
        aria-describedby={description ? 'mk-modal-desc' : undefined}
        onKeyDown={onKeyDown}
        className="mk-modal-in bg-white rounded-2xl max-w-md w-full shadow-2xl border border-neutral-200 p-6 sm:p-8 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 w-16 h-16 rounded-full flex items-center justify-center">
          <div className={`w-16 h-16 rounded-full flex items-center justify-center ${iconWrap}`}>
            <Icon className="w-9 h-9" />
          </div>
        </div>

        <h3 id="mk-modal-title" className="text-lg font-bold text-[#171717]">
          {title}
        </h3>
        {description && (
          <p id="mk-modal-desc" className="mt-2 text-sm text-[#171717] leading-relaxed">
            {description}
          </p>
        )}

        <div className={`mt-6 flex gap-2.5 ${hasConfirm ? 'flex-col sm:flex-row' : ''}`}>
          {hasConfirm && (
            <button
              type="button"
              onClick={dismiss}
              className="flex-1 px-4 py-2.5 bg-white border border-neutral-300 hover:border-[#6C3FC5] hover:bg-[#F3EEFC] text-[#171717] text-sm font-semibold rounded-xl transition-colors"
            >
              {cancelLabel}
            </button>
          )}
          <button
            ref={primaryRef}
            type="button"
            onClick={primaryAction}
            className={`flex-1 px-4 py-2.5 text-sm font-bold rounded-xl shadow-md transition-all active:scale-[0.99] ${primaryBtn}`}
          >
            {hasConfirm ? confirmLabel || 'Confirm' : acknowledgeLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
