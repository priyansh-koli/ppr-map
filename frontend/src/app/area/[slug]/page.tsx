import type { Metadata } from "next";

import { PlaceholderPage, pageMetadata } from "@/components/placeholder-page";

type Props = { params: Promise<{ slug: string }> };

export function generateMetadata(): Metadata {
  return pageMetadata("area");
}

export default async function Page({ params }: Props) {
  const { slug } = await params;
  return <PlaceholderPage routeKey="area" detail={`Area: ${slug}`} />;
}
