"use client";

import { useEffect, useState } from "react";

type Choice = "system" | "light" | "dark";
const KEY = "ppr-theme";
const NEXT: Record<Choice, Choice> = { system: "light", light: "dark", dark: "system" };
const LABEL: Record<Choice, string> = {
  system: "same as this device",
  light: "light",
  dark: "dark",
};

/** Runs before the first paint (layout.tsx), so a chosen theme never flashes the other one. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

function stored(): Choice {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

/** Cycles device → light → dark. The choice is a per-browser convenience in localStorage. */
export function ThemeToggle() {
  const [choice, setChoice] = useState<Choice>("system");
  // eslint-disable-next-line react-hooks/set-state-in-effect -- read once after hydration
  useEffect(() => setChoice(stored()), []);

  const pick = (next: Choice) => {
    setChoice(next);
    const root = document.documentElement;
    if (next === "system") delete root.dataset.theme;
    else root.dataset.theme = next;
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      // Private mode: the choice lasts for this page only.
    }
  };

  return (
    <button
      type="button"
      onClick={() => pick(NEXT[choice])}
      className="grid h-9 w-9 place-items-center rounded-full text-ink-2 hover:bg-fill"
      aria-label={`Theme: ${LABEL[choice]}. Switch to ${LABEL[NEXT[choice]]}`}
      title={`Theme: ${LABEL[choice]}`}
    >
      <svg viewBox="0 0 20 20" className="h-[18px] w-[18px]" aria-hidden="true">
        <circle cx="10" cy="10" r="7.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        {choice === "light" ? null : (
          <path
            d={
              choice === "dark"
                ? "M10 2.75a7.25 7.25 0 0 0 0 14.5Z"
                : "M10 2.75v14.5a7.25 7.25 0 0 0 0-14.5Z"
            }
            fill="currentColor"
          />
        )}
      </svg>
    </button>
  );
}
