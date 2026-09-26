import { PlaceholderPage, pageMetadata } from "@/components/placeholder-page";

export const metadata = pageMetadata("admin");

export default function Page() {
  return <PlaceholderPage routeKey="admin" />;
}
