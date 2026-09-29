import { AlertCircle, Check, LoaderCircle } from "lucide-react";
import type { Job } from "../types/domain";
import { cn } from "../lib/cn";

const labels = {
  queued: "Wartet",
  running: "Wird erstellt",
  completed: "Fertig",
  needs_review: "Prüfung nötig",
  failed: "Fehlgeschlagen",
};

export function StatusPill({ status }: { status: Job["status"] }) {
  const pending = status === "queued" || status === "running";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
        status === "completed" && "bg-emerald-50 text-emerald-700",
        status === "needs_review" && "bg-amber-50 text-amber-700",
        status === "failed" && "bg-red-50 text-red-700",
        pending && "bg-blue-50 text-blue-700",
      )}
    >
      {pending ? (
        <LoaderCircle size={12} className="animate-spin" />
      ) : status === "completed" ? (
        <Check size={12} />
      ) : (
        <AlertCircle size={12} />
      )}
      {labels[status]}
    </span>
  );
}
