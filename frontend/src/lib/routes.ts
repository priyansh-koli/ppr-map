/**
 * Every page in the app. Navigation, page metadata, and the route smoke tests read this list;
 * a unit test checks that each entry has a matching `src/app/.../page.tsx`.
 */
export type Access = "public" | "user" | "admin";

export interface RouteDef {
  /** Next.js path pattern, e.g. `/property/[id]`. */
  path: string;
  /** A concrete URL for smoke tests. */
  samplePath: string;
  title: string;
  summary: string;
  /** Phase in which the real feature lands (docs: phase plan). */
  phase: 1 | 2 | 3 | 4 | 5;
  access: Access;
}

export const ROUTES = {
  home: {
    path: "/",
    samplePath: "/",
    // The hero splits it to highlight "on one map." (components/home/hero.tsx).
    title: "Every home sold in Ireland, on one map.",
    summary:
      "Every residential sale on the Property Price Register since 2010, on a map, with honest locations, sale history and neighbourhood context.",
    phase: 3,
    access: "public",
  },
  map: {
    path: "/map",
    samplePath: "/map",
    title: "Map explorer",
    summary:
      "Clustered sales at low zoom, individual sales up close, hover or tap for details. A synced list view gives keyboard access.",
    phase: 3,
    access: "public",
  },
  search: {
    path: "/search",
    samplePath: "/search",
    title: "Search sales",
    summary:
      "Filter by county, area, Eircode routing key, radius, price, date, new or second-hand, and market-sale flags. Every search has a shareable URL.",
    phase: 5,
    access: "public",
  },
  property: {
    path: "/property/[id]",
    samplePath: "/property/example",
    title: "Property",
    summary:
      "Full sale history, comparable nearby sales, vicinity, planning, environment, area stats, sources and caveats.",
    phase: 3,
    access: "public",
  },
  area: {
    path: "/area/[slug]",
    samplePath: "/area/dublin",
    title: "Area",
    summary:
      "Median price over time, sales volume, price distribution, and comparison with national and CSO figures.",
    phase: 5,
    access: "public",
  },
  tools: {
    path: "/tools",
    samplePath: "/tools",
    title: "Tools",
    summary: "Stamp duty and mortgage affordability calculators.",
    phase: 5,
    access: "public",
  },
  stampDuty: {
    path: "/tools/stamp-duty",
    samplePath: "/tools/stamp-duty",
    title: "Stamp duty calculator",
    summary: "Rates are verified against Revenue before this calculator goes live.",
    phase: 5,
    access: "public",
  },
  affordability: {
    path: "/tools/affordability",
    samplePath: "/tools/affordability",
    title: "Mortgage affordability",
    summary:
      "Based on the Central Bank mortgage measures, verified before launch. Information only, not financial advice.",
    phase: 5,
    access: "public",
  },
  sources: {
    path: "/sources",
    samplePath: "/sources",
    title: "Data sources and methodology",
    summary:
      "Where every number comes from, its licence, how locations are estimated, and what the data cannot tell you.",
    phase: 2,
    access: "public",
  },
  report: {
    path: "/report",
    samplePath: "/report",
    title: "Report an error or request removal",
    summary: "Ask us to correct a location or detail, or to stop displaying an address.",
    phase: 5,
    access: "public",
  },
  privacy: {
    path: "/privacy",
    samplePath: "/privacy",
    title: "Privacy policy",
    summary: "What we collect, why, how long we keep it, and your rights under GDPR.",
    phase: 4,
    access: "public",
  },
  terms: {
    path: "/terms",
    samplePath: "/terms",
    title: "Terms of use",
    summary: "Terms for using this site and its data.",
    phase: 4,
    access: "public",
  },
  login: {
    path: "/login",
    samplePath: "/login",
    title: "Sign in",
    summary: "Sign in with your email and password.",
    phase: 4,
    access: "public",
  },
  register: {
    path: "/register",
    samplePath: "/register",
    title: "Create an account",
    summary:
      "Required: full name, email, password, confirmation you are 18+, and acceptance of the Terms and Privacy Policy. Everything else is optional.",
    phase: 4,
    access: "public",
  },
  verifyEmail: {
    path: "/verify-email",
    samplePath: "/verify-email",
    title: "Verify your email",
    summary: "Alerts switch on once your email address is verified.",
    phase: 4,
    access: "public",
  },
  forgotPassword: {
    path: "/forgot-password",
    samplePath: "/forgot-password",
    title: "Forgot password",
    summary: "We will email you a reset link.",
    phase: 4,
    access: "public",
  },
  resetPassword: {
    path: "/reset-password",
    samplePath: "/reset-password",
    title: "Reset password",
    summary: "Choose a new password.",
    phase: 4,
    access: "public",
  },
  account: {
    path: "/account",
    samplePath: "/account",
    title: "Account settings",
    summary:
      "Profile, password, notification preferences, history on or off, download your data, delete your account.",
    phase: 4,
    access: "user",
  },
  wishlist: {
    path: "/account/wishlist",
    samplePath: "/account/wishlist",
    title: "Wishlist",
    summary: "Saved properties and areas with private notes.",
    phase: 4,
    access: "user",
  },
  compare: {
    path: "/account/wishlist/compare",
    samplePath: "/account/wishlist/compare",
    title: "Compare",
    summary: "Compare up to four saved properties or areas side by side.",
    phase: 4,
    access: "user",
  },
  history: {
    path: "/account/history",
    samplePath: "/account/history",
    title: "History",
    summary:
      "Recently viewed properties and past searches. Clear all, delete items, or turn history off.",
    phase: 4,
    access: "user",
  },
  savedSearches: {
    path: "/account/saved-searches",
    samplePath: "/account/saved-searches",
    title: "Saved searches and alerts",
    summary: "Get an email when a new sale matches your filters.",
    phase: 5,
    access: "user",
  },
  admin: {
    path: "/admin",
    samplePath: "/admin",
    title: "Admin",
    summary: "Data operations, user management and the audit log.",
    phase: 5,
    access: "admin",
  },
  adminIngestRuns: {
    path: "/admin/ingest-runs",
    samplePath: "/admin/ingest-runs",
    title: "Ingest runs",
    summary: "Rows loaded, rows failed, geocode success by confidence level.",
    phase: 2,
    access: "admin",
  },
  adminGeocode: {
    path: "/admin/geocode",
    samplePath: "/admin/geocode",
    title: "Geocode review",
    summary: "Correct low-confidence locations and review property merges.",
    phase: 5,
    access: "admin",
  },
  adminRemovals: {
    path: "/admin/removal-requests",
    samplePath: "/admin/removal-requests",
    title: "Removal and correction requests",
    summary: "Review and decide requests; approved removals hide the address from public views.",
    phase: 5,
    access: "admin",
  },
  adminUsers: {
    path: "/admin/users",
    samplePath: "/admin/users",
    title: "Users",
    summary: "Activate, deactivate and change roles. Every change is audit-logged.",
    phase: 5,
    access: "admin",
  },
  adminAudit: {
    path: "/admin/audit-log",
    samplePath: "/admin/audit-log",
    title: "Audit log",
    summary: "Append-only record of administrative actions.",
    phase: 5,
    access: "admin",
  },
} as const satisfies Record<string, RouteDef>;

export type RouteKey = keyof typeof ROUTES;

export const PRIMARY_NAV: RouteKey[] = ["map", "search", "tools", "sources"];
