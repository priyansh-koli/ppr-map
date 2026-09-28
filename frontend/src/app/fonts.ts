/**
 * Type (D-043), self-hosted by next/font at build time, so pages load no third-party font:
 * Fraunces (a soft serif) for headings and the green italic highlight, IBM Plex Sans for text,
 * IBM Plex Mono for window labels and figures.
 */
import { Fraunces, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

const heading = Fraunces({
  subsets: ["latin", "latin-ext"],
  style: ["normal", "italic"],
  axes: ["opsz", "SOFT"],
  variable: "--font-heading",
  display: "swap",
});
const body = IBM_Plex_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});
const code = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-code",
  display: "swap",
});

export const fontVariables = [heading, body, code].map((f) => f.variable).join(" ");
