/**
 * A fake `/api/v1` for component tests: routes are "METHOD /path" (without the prefix or the
 * query string) and answer with a status and a JSON body. Unrouted calls fail the test.
 */
import type { Me } from "@/lib/api/client";

type Answer = [status: number, body?: unknown] | Promise<[status: number, body?: unknown]>;
export type Routes = Record<string, (init: RequestInit) => Answer>;

export function mockApi(routes: Routes) {
  // The CSRF cookie is already set, so writes do not fetch it first.
  document.cookie = "ppr_csrf=test";
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${(init.method ?? "GET").toUpperCase()} ${url.pathname.replace("/api/v1", "")}`;
    const route = routes[key];
    if (!route) throw new Error(`unexpected request: ${key}`);
    const [status, body] = await route(init);
    return new Response(status === 204 ? null : JSON.stringify(body ?? {}), { status });
  });
  vi.stubGlobal("fetch", fetch);
  /** How many times a route was called. */
  const calls = (key: string) =>
    fetch.mock.calls.filter(([input, init]) => {
      const url = new URL(String(input), "http://localhost");
      return `${(init?.method ?? "GET").toUpperCase()} ${url.pathname.replace("/api/v1", "")}` === key;
    }).length;
  return { fetch, calls };
}

/** A promise with its resolve exposed, to hold an answer back. */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

export const ME: Me = {
  id: "u1",
  email: "aoife@example.ie",
  fullName: "Aoife Byrne",
  emailVerified: true,
  historyEnabled: true,
  marketingOptIn: false,
  createdAt: "2026-09-27T10:00:00Z",
  permissions: [],
  roles: ["user"],
  profile: {
    userType: null,
    propertyInterest: null,
    budgetMin: null,
    budgetMax: null,
    counties: null,
  },
};
