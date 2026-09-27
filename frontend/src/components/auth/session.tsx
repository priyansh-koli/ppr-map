"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { api, ApiError, type Me, STATIC_PREVIEW, UNAUTHORIZED_EVENT } from "@/lib/api/client";

interface SessionState {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<Me | null>;
  /** Ends this session; throws (after re-checking it) if the server did not. */
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
  const signedIn = useRef(false);
  const checking = useRef(false);

  const refresh = useCallback(async () => {
    if (STATIC_PREVIEW) return null;
    try {
      const next = await api.me();
      signedIn.current = true;
      setMe(next);
      return next;
    } catch (e) {
      // Only a 401 means signed out; a network or server error leaves the state as it was.
      if (e instanceof ApiError && e.status === 401) {
        signedIn.current = false;
        setMe(null);
      } else {
        console.warn("session check failed", e);
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch (e) {
      // 401: the session had already ended. Otherwise the cookie may still work (a shared
      // computer), so show what the server says rather than pretend it is signed out.
      if (!(e instanceof ApiError && e.status === 401)) {
        await refresh();
        throw e;
      }
    }
    signedIn.current = false;
    setMe(null);
  }, [refresh]);

  useEffect(() => {
    // The first check runs once on load; later changes go through refresh().
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  useEffect(() => {
    // An authenticated call got a 401 (expired, or signed out elsewhere): re-check the session.
    // A burst of 401s triggers one check, not one each.
    const onUnauthorized = () => {
      if (!signedIn.current || checking.current) return;
      checking.current = true;
      void refresh().finally(() => {
        checking.current = false;
      });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [refresh]);

  const value = useMemo(() => ({ me, loading, refresh, signOut }), [me, loading, refresh, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export const useSession = () => useContext(SessionContext);
