import type { Metadata } from "next";

import { PlaceholderPage, pageMetadata } from "@/components/placeholder-page";

type Props = { params: Promise<{ slug: string }> };

// The static export (D-034) needs every path at build time. Until real areas exist, pre-render
// the sample URL from `routes.ts`; the server build still renders any slug on request.
export function generateStaticParams() {
  return [{ slug: "dublin" }];
}

export function generateMetadata(): Metadata {
  return pageMetadata("area");
}

export default async function Page({ params }: Props) {
  const { slug } = await params;
  return <PlaceholderPage routeKey="area" detail={`Area: ${slug}`} />;
}
