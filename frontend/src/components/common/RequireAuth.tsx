'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldAlert, Loader2 } from 'lucide-react';
import { authHeaders, clearAuthSession, getAuthToken, loginUrlFor } from '@/lib/auth';

/**
 * QA BUG-003: client-side session guard for the staff workstations.
 *
 * The backend already refuses every data call without a valid token (401) and
 * for a disallowed role (403) — that enforcement is unchanged. Before this
 * guard, /doctor and /admin still RENDERED the full clinical shell for an
 * anonymous visitor and silently discarded the 401s, which produced a
 * convincing "empty workstation". This component checks the session against
 * GET /api/auth/me (role comes from the database, not from localStorage) and
 * shows an explicit state instead.
 *
 * Redirects target /login?next=<this page> and never run when the browser is
 * already on /login, so no redirect loop is possible.
 */

type GuardState = 'checking' | 'authorized' | 'unauthenticated' | 'forbidden' | 'offline';

interface RequireAuthProps {
  /** Roles allowed to view the wrapped content (server-side RBAC still applies). */
  allowedRoles: string[];
  children: React.ReactNode;
}

function Panel({
  title,
  body,
  tone = 'neutral',
  children,
}: {
  title: string;
  body: string;
  tone?: 'neutral' | 'warn';
  children?: React.ReactNode;
}) {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4 py-12">
      <div
        className={`max-w-md w-full rounded-xl border p-6 space-y-3 ${
          tone === 'warn' ? 'border-amber-200 bg-amber-50' : 'border-neutral-200 bg-white'
        }`}
      >
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-5 h-5 text-[#6C3FC5]" />
          <h2 className="text-base font-bold text-[#171717]">{title}</h2>
        </div>
        <p className="text-xs sm:text-sm text-[#666666] leading-relaxed">{body}</p>
        {children}
      </div>
    </div>
  );
}

export function RequireAuth({ allowedRoles, children }: RequireAuthProps) {
  const router = useRouter();
  const [state, setState] = useState<GuardState>('checking');
  const [identity, setIdentity] = useState<{ name: string; role: string } | null>(null);
  const roleKey = allowedRoles.join('|');

  useEffect(() => {
    let cancelled = false;
    const target = loginUrlFor(window.location.pathname, window.location.search);

    const token = getAuthToken();
    if (!token) {
      setState('unauthenticated');
      router.replace(target);
      return;
    }

    fetch('/api/auth/me', { headers: authHeaders() })
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 401) {
          // Expired / revoked token: drop it and ask for credentials again.
          clearAuthSession();
          setState('unauthenticated');
          router.replace(target);
          return;
        }
        if (!res.ok) {
          setState('offline');
          return;
        }
        const me = await res.json();
        if (cancelled) return;
        setIdentity({ name: me?.name || 'Signed-in user', role: me?.role || 'UNKNOWN' });
        setState(allowedRoles.includes(me?.role) ? 'authorized' : 'forbidden');
      })
      .catch(() => {
        if (!cancelled) setState('offline');
      });

    return () => {
      cancelled = true;
    };
    // allowedRoles is passed as an inline array literal, so depend on its
    // joined value; re-running on the array itself would loop every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleKey, router]);

  if (state === 'authorized') return <>{children}</>;

  if (state === 'checking') {
    return (
      <div className="min-h-[60vh] flex items-center justify-center gap-2 text-xs sm:text-sm text-[#666666]">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Verifying your session...</span>
      </div>
    );
  }

  if (state === 'unauthenticated') {
    return (
      <Panel
        title="Sign-in required"
        body="This workstation shows patient data, so it is not available without a staff sign-in. You are being redirected to the sign-in page."
      >
        <button
          type="button"
          onClick={() => router.replace(loginUrlFor(window.location.pathname, window.location.search))}
          className="mt-1 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-[#6C3FC5] hover:bg-[#4B238C] text-white transition-colors"
        >
          Go to sign-in now
        </button>
      </Panel>
    );
  }

  if (state === 'forbidden') {
    return (
      <Panel
        tone="warn"
        title="Your account cannot open this area"
        body={`Signed in as ${identity?.name ?? 'unknown user'} (${identity?.role ?? 'UNKNOWN'}). This area is restricted to ${allowedRoles.join(' or ')}. No patient data was loaded.`}
      >
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            // QA-08: switching accounts used to drop ?next=, so signing in as
            // the correct role landed on that role's default page instead of
            // the area the user actually asked for.
            onClick={() => router.replace(loginUrlFor(window.location.pathname, window.location.search))}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-[#6C3FC5] hover:bg-[#4B238C] text-white transition-colors"
          >
            Sign in with another account
          </button>
          <button
            type="button"
            onClick={() => router.replace('/')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold border border-neutral-300 text-neutral-700 hover:bg-neutral-100 transition-colors"
          >
            Return to overview
          </button>
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      tone="warn"
      title="Cannot reach the MediKiosk server"
      body="Your session could not be verified because the backend did not respond. Patient data is not shown until the check succeeds."
    >
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="mt-1 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-[#6C3FC5] hover:bg-[#4B238C] text-white transition-colors"
      >
        Retry
      </button>
    </Panel>
  );
}
