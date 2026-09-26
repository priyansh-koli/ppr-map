import type { Metadata } from "next";

import { PlaceholderPage, pageMetadata } from "@/components/placeholder-page";

type Props = { params: Promise<{ id: string }> };

export function generateMetadata(): Metadata {
  return pageMetadata("property");
}

export default async function Page({ params }: Props) {
  const { id } = await params;
  return <PlaceholderPage routeKey="property" detail={`ID: ${id}`} />;
}
