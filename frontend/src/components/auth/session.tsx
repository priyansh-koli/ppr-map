"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, ApiError, type Me, STATIC_PREVIEW } from "@/lib/api/client";

interface SessionState {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<Me | null>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionState>({
  me: null,
  loading: false,
  refresh: async () => null,
  signOut: async () => {},
});

/** Who is signed in, from `/api/v1/me`. The API enforces access; this only shapes the UI. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(!STATIC_PREVIEW);

  const refresh = useCallback(async () => {
    if (STATIC_PREVIEW) return null;
    try {
      const next = await api.me();
      setMe(next);
      return next;
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) console.warn("session check failed", e);
      setMe(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    await api.logout().catch(() => {});
    setMe(null);
  }, []);

  useEffect(() => {
    // The first check runs once on load; later changes go through refresh().
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const value = useMemo(() => ({ me, loading, refresh, signOut }), [me, loading, refresh, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export const useSession = () => useContext(SessionContext);
