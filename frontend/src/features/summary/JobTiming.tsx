import { useEffect, useState } from "react";
import type { Job } from "../../shared/types/domain";

function duration(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours ? `${hours} Std. ` : ""}${minutes} Min. ${seconds % 60} Sek.`;
}

export function JobTiming({ job }: { job: Job }) {
  const [clock, setClock] = useState(Date.now);
  const active = job.status === "queued" || job.status === "running";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const start = job.started_at ?? job.created_at;
  const end = job.finished_at ? Date.parse(job.finished_at) : clock;
  const elapsed = end - Date.parse(start);
  if (!Number.isFinite(elapsed)) return null;
  const label =
    job.status === "queued"
      ? "Wartezeit"
      : job.started_at
        ? active
          ? "Laufzeit bisher"
          : "Auswertungsdauer"
        : "Gesamtzeit inkl. Warteschlange";
  return (
    <p className="mt-3 text-xs text-zinc-500">
      {label}: {duration(elapsed)}
    </p>
  );
}
