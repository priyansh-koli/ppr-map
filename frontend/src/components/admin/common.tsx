"use client";

import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { useSession } from "@/components/auth/session";
import { SignInLink } from "@/components/auth/sign-in-link";
import { type PageOf, STATIC_PREVIEW } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";

import { messageOf } from "../auth/form";

/** Admin pages: the API enforces access; this only avoids showing a page that will fail. */
export function RequireAdmin({ perm, children }: { perm: string; children: ReactNode }) {
  const { me, loading } = useSession();
  if (STATIC_PREVIEW) return <p className="text-muted">Admin needs the data server.</p>;
  if (loading) return <p className="text-muted">Loading…</p>;
  if (!me)
    return (
      <p>
        <SignInLink className="font-medium text-accent underline">Sign in</SignInLink> with an admin
        account.
      </p>
    );
  if (!me.permissions.includes(perm)) return <p>Your account cannot use this page.</p>;
  return <>{children}</>;
}

const ADMIN_PAGES = [
  ROUTES.adminIngestRuns,
  ROUTES.adminGeocode,
  ROUTES.adminRemovals,
  ROUTES.adminUsers,
  ROUTES.adminAudit,
];

export function AdminNav({ current }: { current: string }) {
  return (
    <nav aria-label="Admin" className="flex flex-wrap gap-1 text-sm">
      <Link
        href={ROUTES.admin.path}
        aria-current={current === ROUTES.admin.path ? "page" : undefined}
        className="rounded-full px-3 py-1.5 hover:bg-fill aria-[current=page]:bg-ink aria-[current=page]:text-surface"
      >
        Overview
      </Link>
      {ADMIN_PAGES.map((r) => (
        <Link
          key={r.path}
          href={r.path}
          aria-current={current === r.path ? "page" : undefined}
          className="rounded-full px-3 py-1.5 hover:bg-fill aria-[current=page]:bg-ink aria-[current=page]:text-surface"
        >
          {r.title}
        </Link>
      ))}
    </nav>
  );
}

/** A server-paged list: `load(page)` for the current key; reload() after a change. */
export function usePage<T>(load: (page: number) => Promise<PageOf<T>>, key: string) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState<{ key: string; data?: PageOf<T>; error?: string }>({
    key: "",
  });
  const [tick, setTick] = useState(0);
  const want = `${key}|${page}|${tick}`;
  useEffect(() => {
    let live = true;
    load(page)
      .then((data) => live && setState({ key: want, data }))
      .catch((e: unknown) => live && setState({ key: want, error: messageOf(e) }));
    return () => {
      live = false;
    };
  }, [load, page, want]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  // A new key (a filter) starts again at page 1.
  const [lastKey, setLastKey] = useState(key);
  if (key !== lastKey) {
    setLastKey(key);
    setPage(1);
  }
  return { ...state, loading: state.key !== want, page, setPage, reload };
}

export function Pager({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav aria-label="Pages" className="mt-4 flex items-center gap-3 text-sm">
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </button>
      <span className="text-muted">
        Page {page} of {pages.toLocaleString("en-IE")} ({total.toLocaleString("en-IE")})
      </span>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </nav>
  );
}

export const th = "py-2 pr-3 text-left font-medium text-muted";
export const td = "py-2 pr-3 align-top";
