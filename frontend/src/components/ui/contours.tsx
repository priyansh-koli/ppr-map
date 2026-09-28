/**
 * Faint map contour lines, drawn from a fixed formula so the server and the browser render the
 * same paths. Decoration only: the home hero sits on them, like a survey sheet.
 */
function ring(cx: number, cy: number, r: number, seed: number): string {
  const points: string[] = [];
  for (let i = 0; i <= 72; i++) {
    const a = (i / 72) * Math.PI * 2;
    const wobble =
      1 +
      0.09 * Math.sin(3 * a + seed) +
      0.05 * Math.sin(5 * a + seed * 1.7) +
      0.03 * Math.sin(9 * a + seed * 0.6);
    const x = cx + Math.cos(a) * r * wobble * 1.35;
    const y = cy + Math.sin(a) * r * wobble;
    points.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  return `${points.join(" ")}Z`;
}

const PATHS = [
  ...Array.from({ length: 9 }, (_, k) => ring(930, 250, 40 + k * 34, 0.8 + k * 0.35)),
  ...Array.from({ length: 6 }, (_, k) => ring(160, 520, 30 + k * 36, 2.1 + k * 0.4)),
];

export function Contours({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 1200 700"
      preserveAspectRatio="xMidYMid slice"
      className={`pointer-events-none absolute inset-0 h-full w-full text-line-strong [mask-image:radial-gradient(ellipse_at_center,black_35%,transparent_80%)] ${className}`}
    >
      {PATHS.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke="currentColor"
          strokeWidth={i % 4 === 0 ? 1.4 : 0.8}
          opacity={0.9}
        />
      ))}
    </svg>
  );
}
