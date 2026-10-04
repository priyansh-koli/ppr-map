import { ApiError, type PropertyList } from "@/lib/api/client";

export type ListState =
  | { status: "zoom" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ok"; data: PropertyList };

// The API's answer for a box too large to list (/api/v1/properties).
const ZOOM_IN = "Zoom in to list sales";

type Fetch = (query: URLSearchParams, init: { signal: AbortSignal }) => Promise<PropertyList>;

/**
 * The synced list for the latest view only. A slower answer for where the map was must never
 * replace the current state, the "zoom in" one included: a request still open when the map
 * zooms out used to land on top of it and list sales from a view the map had left.
 */
export function listLoader(fetchList: Fetch, setList: (state: ListState) => void) {
  let current: AbortController | null = null;
  return {
    zoomedOut() {
      current?.abort();
      current = null;
      setList({ status: "zoom" });
    },
    load(query: URLSearchParams) {
      current?.abort();
      const request = new AbortController();
      current = request;
      setList({ status: "loading" });
      fetchList(query, { signal: request.signal })
        .then((data) => {
          if (!request.signal.aborted) setList({ status: "ok", data });
        })
        .catch((e: unknown) => {
          if (request.signal.aborted) return;
          setList(
            e instanceof ApiError && e.status === 422 && e.detail === ZOOM_IN
              ? { status: "zoom" }
              : { status: "error", message: "The list could not be loaded." },
          );
        });
    },
    stop() {
      current?.abort();
      current = null;
    },
  };
}
