// Phase 6: client-side bearer-token helper.
//
// The login page persists the JWT issued by POST /api/auth/login under
// 'medikiosk_token'. Doctor and admin workstations MUST send it on every
// backend call — the server now enforces strict authentication on all
// patient-data endpoints (401 without a token, 403 for a disallowed role).
//
// Reading the token is defensive: SSR (no window) and private-mode storage
// failures simply produce no Authorization header, and the calling UI falls
// back to its existing local/demo behavior.

export const TOKEN_KEY = 'medikiosk_token';
export const USER_KEY = 'medikiosk_user';

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Merge an Authorization header (when a token exists) into optional extra headers. */
export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getAuthToken();
  const headers = { ...extra };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

/** Clear the stored staff session. Used on 401 and by the sign-out control. */
export function clearAuthSession(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    /* storage unavailable - nothing to clear */
  }
}

/**
 * End the current staff session on this device and return to sign-in.
 *
 * MediKiosk issues stateless JWT bearer tokens (backend auth_router) and the
 * API exposes NO logout/revocation endpoint, so sign-out is intentionally
 * client-side only: we drop the stored token + user so no protected call can
 * re-use them, and the caller redirects to /login. The token itself simply
 * expires on its own schedule (ACCESS_TOKEN_EXPIRE_MINUTES). This is the single
 * shared logout path for every staff workstation, clears ONLY the session
 * (never shared kiosk/patient state), and — importantly — does not claim the
 * token was revoked on the server, because it cannot be.
 */
export function signOutStaff(): void {
  clearAuthSession();
}

/**
 * QA BUG-003: build the sign-in location for a protected page, keeping the
 * destination. Only same-origin absolute paths are accepted, so a crafted
 * ?next=... can never send the user to another host.
 */
export function loginUrlFor(pathname: string, search = ''): string {
  const destination = `${pathname}${search}`;
  const safe = pathname.startsWith('/') && !pathname.startsWith('//');
  return safe ? `/login?next=${encodeURIComponent(destination)}` : '/login';
}

/**
 * Entry URL for a staff workstation (shared-kiosk rule).
 *
 * "Physician OPD" and "Admin & Triage" ALWAYS pass through the sign-in screen:
 * a stored staff session never opens a workstation on its own, so every entry
 * is an explicit authentication. ?next keeps the intended destination and
 * ?role preselects the matching sign-in tab. Neither value is trusted —
 * RequireAuth revalidates the token against GET /api/auth/me and the backend
 * revalidates the role on every protected call.
 */
export function staffEntryUrl(target: '/doctor' | '/admin'): string {
  const role = target === '/admin' ? 'ADMIN' : 'DOCTOR';
  return `${loginUrlFor(target)}&role=${role}`;
}

/**
 * Whether a staff role may open a protected path. Mirrors the allowedRoles on
 * the guarded pages so a DOCTOR is never forwarded to /admin by a stale or
 * crafted ?next= (which would otherwise bounce between the guard and sign-in).
 */
export function roleCanOpen(role: string | undefined, target: string): boolean {
  const path = target.split('?')[0].split('#')[0];
  if (path === '/admin' || path.startsWith('/admin/')) return role === 'ADMIN';
  if (path === '/doctor' || path.startsWith('/doctor/')) return role === 'DOCTOR' || role === 'ADMIN';
  return true;
}

/** Read a safe ?next= target out of a login URL's query string. */
export function safeNextTarget(searchParams: URLSearchParams): string | null {
  const next = searchParams.get('next');
  if (!next) return null;
  if (!next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return null;
  if (next.startsWith('/login')) return null;
  return next;
}

/**
 * fetch() wrapper for staff API calls. A 401 means the stored token is
 * missing, expired or revoked: the session is cleared and the browser is sent
 * to the sign-in page instead of rendering an empty "fake" workstation.
 * The response is returned untouched so callers can still handle 403/5xx.
 */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(input, { ...init, headers: authHeaders(init.headers as Record<string, string> | undefined) });
  if (res.status === 401 && typeof window !== 'undefined') {
    clearAuthSession();
    const here = window.location.pathname + window.location.search;
    if (!here.startsWith('/login')) window.location.replace(loginUrlFor(window.location.pathname, window.location.search));
  }
  return res;
}
