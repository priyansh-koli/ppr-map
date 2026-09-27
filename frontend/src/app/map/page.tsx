import { MapExplorer } from "@/components/map/map-explorer";
import { pageMetadata } from "@/components/placeholder-page";
import { ROUTES } from "@/lib/routes";

export const metadata = pageMetadata("map");

export default function Page() {
  return (
    <>
      <h1 className="sr-only">{ROUTES.map.title}</h1>
      <MapExplorer />
    </>
  );
}
