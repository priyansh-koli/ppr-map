/**
 * Stack tests register several accounts from one IP, which the real limits (5 sign-ups per
 * hour, docs/permissions.md) would refuse on a second run. Before the run, delete only the
 * rate-limit counters in the local Redis (published on 127.0.0.1:6379 by docker compose).
 */
import { connect } from "node:net";

const SCRIPT = "for _, k in ipairs(redis.call('KEYS', 'ratelimit:*')) do redis.call('DEL', k) end";

function resp(args: string[]): string {
  return `*${args.length}\r\n${args.map((a) => `$${Buffer.byteLength(a)}\r\n${a}\r\n`).join("")}`;
}

export default async function globalSetup(): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const socket = connect(6379, "127.0.0.1", () => socket.write(resp(["EVAL", SCRIPT, "0"])));
    // A RESP reply starts with its type: "+" status, ":" integer, "*" array, "$" bulk string
    // (nil for this script) are fine; "-" is an error such as NOAUTH, which must stop the run.
    socket.once("data", (reply) => {
      socket.end();
      const text = reply.toString();
      if ("+:*$".includes(text[0] ?? "-")) resolve();
      else reject(new Error(`Redis refused the rate-limit reset: ${text.trim()}`));
    });
    socket.once("error", reject);
  });
}
