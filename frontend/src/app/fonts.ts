/**
 * Type (D-043), self-hosted by next/font at build time, so pages load no third-party font:
 * Bricolage Grotesque for headings, Instrument Sans for text, IBM Plex Mono for window bars
 * and figures, Caveat for the few handwritten notes.
 */
import { Bricolage_Grotesque, Caveat, IBM_Plex_Mono, Instrument_Sans } from "next/font/google";

const heading = Bricolage_Grotesque({
  subsets: ["latin", "latin-ext"],
  variable: "--font-heading",
  display: "swap",
});
const body = Instrument_Sans({
  subsets: ["latin", "latin-ext"],
  variable: "--font-body",
  display: "swap",
});
const code = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-code",
  display: "swap",
});
const note = Caveat({ subsets: ["latin"], variable: "--font-note", display: "swap" });

export const fontVariables = [heading, body, code, note].map((f) => f.variable).join(" ");
