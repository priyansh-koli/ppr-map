import "@testing-library/jest-dom/vitest";

// Components use the App Router's hooks; unit tests render them without a router.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  notFound: () => {
    throw new Error("notFound");
  },
}));

// next/font runs only in the Next.js compiler; tests need just the class names.
vi.mock("@/app/fonts", () => ({ fontVariables: "" }));
