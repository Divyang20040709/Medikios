'use client';

import React, { useCallback, useEffect, useRef } from 'react';

/**
 * Shared modal-dialog behaviour (QA-12).
 *
 * The three display-only modals (Help, Database Schema, FHIR Bundle) and the
 * consultation-completed confirmation were plain <div>s: a keyboard or screen
 * reader user could not tell a dialog had opened, Escape did nothing, focus
 * stayed behind the overlay and tabbing walked straight into the page beneath.
 *
 * NotificationModal keeps its own inline implementation (it also owns the
 * tone/button layout); this hook supplies the same guarantees to the remaining
 * modals without duplicating a component:
 *   - Escape closes (only when the caller allows it),
 *   - Tab / Shift+Tab cycle inside the dialog,
 *   - focus moves into the dialog on open and returns to the trigger on close.
 *
 * Callers must put `dialogRef` on the element carrying role="dialog" and give
 * that element an id referenced by aria-labelledby.
 */

/**
 * Return focus to wherever it came from.
 *
 * If the trigger was unmounted while the dialog was open — the common case is a
 * modal opened from a mobile nav drawer that closes itself — focusing it is a
 * no-op and the keyboard user is dropped at the document root. Fall back to the
 * main landmark so tabbing resumes at the top of the page content instead.
 */
function restoreFocus(opener: HTMLElement | null) {
  // `body` is not a real opener: when the trigger unmounts before the dialog
  // opens (a nav drawer that closes itself), activeElement has already fallen
  // back to body, and focus() on body is a silent no-op.
  if (opener && opener !== document.body && opener.isConnected) {
    opener.focus?.();
    return;
  }
  const fallback = document.querySelector<HTMLElement>('main');
  if (!fallback) return;
  const alreadyFocusable = fallback.hasAttribute('tabindex');
  if (!alreadyFocusable) fallback.setAttribute('tabindex', '-1');
  fallback.focus({ preventScroll: true });
  if (!alreadyFocusable) {
    fallback.addEventListener(
      'blur',
      () => fallback.removeAttribute('tabindex'),
      { once: true }
    );
  }
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export interface ModalDialogOptions {
  /** Close handler. Omit to make the dialog non-dismissible by Escape/backdrop. */
  onClose?: () => void;
  /** Whether a backdrop click closes the dialog. Default: true. */
  closeOnBackdrop?: boolean;
  /** Element focused on open. Defaults to the first focusable child. */
  initialFocusRef?: React.RefObject<HTMLElement>;
}

export function useModalDialog(
  open: boolean,
  { onClose, closeOnBackdrop = true, initialFocusRef }: ModalDialogOptions = {}
) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const lastFocused = useRef<HTMLElement | null>(null);

  // Move focus in on open, restore it on close.
  useEffect(() => {
    if (!open) return;
    lastFocused.current = document.activeElement as HTMLElement | null;
    const id = window.setTimeout(() => {
      const target =
        initialFocusRef?.current ??
        dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ??
        dialogRef.current;
      target?.focus?.();
    }, 20);
    return () => {
      window.clearTimeout(id);
      restoreFocus(lastFocused.current);
    };
  }, [open, initialFocusRef]);

  // Document-level keyboard handling: works even if focus has drifted outside.
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (!onClose) return;
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }

      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      ).filter((node) => node.offsetParent !== null || node === document.activeElement);
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [open, onClose]);

  const onBackdropClick = useCallback(
    (event: React.MouseEvent) => {
      if (closeOnBackdrop && event.target === event.currentTarget) onClose?.();
    },
    [closeOnBackdrop, onClose]
  );

  return { dialogRef, onBackdropClick };
}
