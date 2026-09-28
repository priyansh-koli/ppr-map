/** The legal pages describe what the app does; who operates it is not decided yet. */
export function DraftNotice() {
  return (
    <p role="note" className="rounded-[10px] bg-accent-wash p-4 text-sm text-ink">
      <span className="font-semibold">Draft.</span> This page describes how the app works today. It
      becomes final once the operator&apos;s name and contact details are added and it has been
      reviewed before launch.
    </p>
  );
}
