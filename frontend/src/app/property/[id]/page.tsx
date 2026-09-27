import type { Metadata } from "next";

import { PlaceholderPage, pageMetadata } from "@/components/placeholder-page";

type Props = { params: Promise<{ id: string }> };

// The static export (D-034) needs every path at build time. Until real properties exist,
// pre-render the sample URL from `routes.ts`; the server build still renders any id on request.
export function generateStaticParams() {
  return [{ id: "example" }];
}

export function generateMetadata(): Metadata {
  return pageMetadata("property");
}

export default async function Page({ params }: Props) {
  const { id } = await params;
  return <PlaceholderPage routeKey="property" detail={`ID: ${id}`} />;
}
