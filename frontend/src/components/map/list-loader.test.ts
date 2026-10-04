import type { PropertyList } from "@/lib/api/client";
import { deferred } from "@/test-fixtures/api";

import { listLoader, type ListState } from "./list-loader";

const PAGE = (total: number): PropertyList => ({ items: [], total, page: 1, pageSize: 50 });

describe("listLoader", () => {
  it("keeps the zoom-in state when an answer for the closer view arrives late", async () => {
    const answer = deferred<PropertyList>();
    const states: ListState[] = [];
    const lists = listLoader(
      () => answer.promise,
      (s) => states.push(s),
    );
    lists.load(new URLSearchParams("bbox=-6.3,53.3,-6.2,53.4"));
    lists.zoomedOut();
    answer.resolve(PAGE(40));
    await answer.promise;
    await Promise.resolve();
    expect(states.map((s) => s.status)).toEqual(["loading", "zoom"]);
  });

  it("shows only the latest view's answer", async () => {
    const first = deferred<PropertyList>();
    const second = deferred<PropertyList>();
    const answers = [first.promise, second.promise];
    const states: ListState[] = [];
    const lists = listLoader(
      () => answers.shift()!,
      (s) => states.push(s),
    );
    lists.load(new URLSearchParams("bbox=a"));
    lists.load(new URLSearchParams("bbox=b"));
    second.resolve(PAGE(2));
    first.resolve(PAGE(1));
    await Promise.all([first.promise, second.promise]);
    await Promise.resolve();
    expect(states.at(-1)).toEqual({ status: "ok", data: PAGE(2) });
    expect(states.filter((s) => s.status === "ok")).toHaveLength(1);
  });
});
