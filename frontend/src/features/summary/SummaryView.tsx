import { ReceiptNotices } from "./ReceiptNotices";
import { ReviewDialog } from "./ReviewDialog";
import { AlertCircle, Check } from "lucide-react";
import { useState } from "react";
import { cn } from "../../shared/lib/cn";
import { formatMoney } from "../../shared/lib/format";
import type { Summary } from "../../shared/types/domain";
import { EmptyState } from "../../shared/ui/EmptyState";
import { StatusPill } from "../../shared/ui/StatusPill";
import { CategoryCard } from "./CategoryCard";
import { ExpenseTable } from "./ExpenseTable";

export function SummaryView({ summary }: { summary: Summary }) {
  const [tab, setTab] = useState<"overview" | "expenses" | "review">(
    "overview",
  );
  const [editing, setEditing] = useState(false);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const reviewDocument = summary.documents.find(
    (document) => document.document_id === reviewId,
  );
  const reviewGroups = summary.documents
    .map((document) => ({
      document,
      warnings: [
        ...new Set(
          summary.warnings
            .filter((w) => w.document_id === document.document_id)
            .map((w) => w.message),
        ),
      ],
    }))
    .filter((group) => group.warnings.length > 0);
  const openReview = (id: string) => {
    setEditing(false);
    setReviewId(id);
  };
  return (
    <section className="space-y-5">
      {reviewDocument && (
        <ReviewDialog
          key={reviewDocument.document_id}
          summary={summary}
          document={reviewDocument}
          initiallyEditing={editing}
          onClose={() => setReviewId(null)}
        />
      )}
      {summary.is_stale && (
        <div className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertCircle className="mt-0.5 shrink-0" size={18} />
          <span>
            Seit dieser Auswertung wurden weitere Belege hinzugefügt. Erstelle
            eine neue Auswertung, um sie einzubeziehen.
          </span>
        </div>
      )}
      <div className="card p-5 sm:p-6">
        <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <StatusPill status={summary.status} />
              <span className="text-xs text-zinc-400">
                {summary.coverage.processed} von {summary.coverage.supplied}{" "}
                Belegen verarbeitet
              </span>
            </div>
            <h2 className="text-xl font-bold tracking-tight">Auswertung</h2>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-3">
          {[
            ...(summary.totals.eur ?? []),
            ...summary.totals.by_currency.filter(
              (total) => total.currency !== "EUR",
            ),
          ].map((total) => (
            <div
              key={total.currency ?? "unknown"}
              className="rounded-2xl bg-ink p-5 text-white"
            >
              <p className="text-xs font-semibold text-zinc-400">
                {total.unknown_amounts > 0 ? "Teilsumme" : "Gesamtsumme"} ·{" "}
                {total.currency ?? "ohne Währung"}
              </p>
              <p className="mt-2 text-2xl font-bold tracking-tight">
                {formatMoney(total.confirmed, total.currency)}
              </p>
              {Number(total.excluded || 0) !== 0 && (
                <p className="mt-2 text-xs text-zinc-300">
                  {formatMoney(total.excluded, total.currency)} abgelehnt
                </p>
              )}
              {(Number(total.in_review) !== 0 || total.unknown_amounts > 0) && (
                <p className="mt-3 text-xs text-zinc-300">
                  {formatMoney(total.in_review, total.currency)} in Prüfung ·{" "}
                  {total.unknown_amounts} ohne Betrag
                </p>
              )}
            </div>
          ))}
          {!summary.totals.by_currency.length && (
            <p className="text-sm text-zinc-500">
              Noch keine Beträge verfügbar.
            </p>
          )}
        </div>
      </div>
      <ReceiptNotices notices={summary.notices ?? []} onReview={openReview} />
      <div className="flex gap-1 overflow-x-auto rounded-xl bg-zinc-200/60 p-1 sm:w-fit">
        {(
          [
            ["overview", "Übersicht"],
            ["expenses", `Ausgaben (${summary.expenses.length})`],
            ["review", `Prüfung (${reviewGroups.length} Belege)`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "focus-ring whitespace-nowrap rounded-lg px-4 py-2 text-sm font-semibold transition",
              tab === key
                ? "bg-white text-ink shadow-sm"
                : "text-zinc-500 hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,180px),1fr))] gap-3">
          {(summary.totals.by_category_eur ?? summary.totals.by_category).map(
            (row) => (
              <CategoryCard key={`${row.currency}-${row.category}`} row={row} />
            ),
          )}
        </div>
      )}
      {tab === "expenses" && (
        <ExpenseTable
          expenses={summary.expenses}
          onReview={openReview}
          onEdit={(id) => {
            setEditing(true);
            setReviewId(id);
          }}
        />
      )}
      {tab === "review" && (
        <div className="card overflow-hidden">
          {reviewGroups.length ? (
            <div className="divide-y divide-line">
              {reviewGroups.map(({ document, warnings }) => (
                <div key={document.document_id} className="p-5">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <h3 className="font-semibold">
                      {document.filename}{" "}
                      <span className="text-xs text-zinc-500">
                        · {warnings.length} Hinweise
                      </span>
                    </h3>
                    <div className="flex gap-3 text-sm text-moss-700">
                      <button
                        className="focus-ring underline"
                        onClick={() => openReview(document.document_id)}
                      >
                        Prüfen / bestätigen
                      </button>
                      <button
                        className="focus-ring underline"
                        onClick={() => {
                          setEditing(true);
                          setReviewId(document.document_id);
                        }}
                      >
                        Bearbeiten
                      </button>
                    </div>
                  </div>
                  <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-zinc-700">
                    {warnings.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={Check} title="Keine Auffälligkeiten" />
          )}
        </div>
      )}
    </section>
  );
}
