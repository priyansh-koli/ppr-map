import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-semibold">Page not found</h1>
      <p className="mt-4">
        <Link className="underline" href="/">
          Back to the home page
        </Link>
      </p>
    </div>
  );
}
