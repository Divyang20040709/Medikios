import { AccessibilitySettings } from './types';

/**
 * Kiosk font-size presets. The banner's A / A+ / A++ buttons used to relabel
 * themselves without changing anything on screen, because the wrapper class
 * only affected text that did not declare its own size (on the staff pages it
 * was not applied at all). Scaling the document root is the honest fix: every
 * rem-based Tailwind size in the tree grows together, on every route.
 */
export const TEXT_SCALE: Record<AccessibilitySettings['textSize'], string> = {
  normal: '100%',
  large: '113%',
  'extra-large': '125%',
};

export function applyTextSize(size: AccessibilitySettings['textSize']) {
  if (typeof document === 'undefined') return;
  document.documentElement.style.fontSize = TEXT_SCALE[size] ?? TEXT_SCALE.normal;
}

/** Root wrapper classes for the remaining accessibility setting (contrast). */
export function accessibilityClasses(settings: AccessibilitySettings): string {
  return settings.highContrast ? 'contrast-125 saturate-150' : '';
}
