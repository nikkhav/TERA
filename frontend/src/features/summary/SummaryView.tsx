import { RelationshipDialog } from "./RelationshipDialog";
import {
  duplicateWarning,
  expenseRows,
  reviewTasks,
  relatedGroup,
} from "./groups";
import { documentKinds, reviewSummary } from "./review";
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
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const reviewDocument = summary.documents.find(
    (document) => document.document_id === reviewId,
  );
  const reviewGroups = reviewTasks(summary);
  const openReview = (id: string) => {
    setComparisonIds([]);
    setEditing(false);
    setReviewId(id);
  };
  return (
    <section className="space-y-5">
      {comparisonIds.length > 1 && (
        <RelationshipDialog
          summary={summary}
          documents={summary.documents.filter((d) =>
            comparisonIds.includes(d.document_id),
          )}
          onClose={() => setComparisonIds([])}
          onOpenDocument={openReview}
        />
      )}
      {reviewDocument && (
        <ReviewDialog
          key={reviewDocument.document_id}
          summary={summary}
          document={reviewDocument}
          initiallyEditing={editing}
          onClose={() => setReviewId(null)}
          onOpenDocument={openReview}
          onCompare={() => {
            setComparisonIds(
              relatedGroup(summary, reviewDocument.document_id).map(
                (d) => d.document_id,
              ),
            );
            setReviewId(null);
          }}
        />
      )}
      {summary.is_stale && (
        <div className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertCircle className="mt-0.5 shrink-0" size={18} />
          <span>
            Die Belege dieser Reise haben sich geändert. Erstelle eine neue
            Auswertung, um die aktuellen Dokumente zu berücksichtigen.
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
      {summary.documents.some(
        (document) =>
          document.duplicate_of ||
          ["payment", "booking", "supporting"].includes(
            document.facts.document_kind ?? "",
          ),
      ) && (
        <details className="card p-5 text-sm">
          <summary className="cursor-pointer font-semibold">
            Weitere Nachweise · nicht zusätzlich summiert
          </summary>
          <ul className="mt-3 space-y-2">
            {summary.documents
              .filter(
                (document) =>
                  document.duplicate_of ||
                  ["payment", "booking", "supporting"].includes(
                    document.facts.document_kind ?? "",
                  ),
              )
              .map((document) => (
                <li key={document.document_id}>
                  <button
                    className="text-moss-700 underline"
                    onClick={() => openReview(document.document_id)}
                  >
                    {document.filename}
                  </button>
                  <span className="ml-2 text-zinc-500">
                    {documentKinds[document.facts.document_kind ?? "unknown"]}
                    {document.duplicate_of
                      ? " · zusätzlicher Nachweis derselben Ausgabe"
                      : ""}
                  </span>
                </li>
              ))}
          </ul>
        </details>
      )}
      <div className="flex gap-1 overflow-x-auto rounded-xl bg-zinc-200/60 p-1 sm:w-fit">
        {(
          [
            ["overview", "Übersicht"],
            ["expenses", `Ausgaben (${expenseRows(summary).length})`],
            ["review", `Prüfung (${reviewGroups.length})`],
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
          summary={summary}
          onReview={openReview}
          onCompare={(ids) => setComparisonIds(ids)}
        />
      )}
      {tab === "review" && (
        <div className="card overflow-hidden">
          {reviewGroups.length ? (
            <div className="divide-y divide-line">
              {reviewGroups.map(({ documents, isRelationship }) => {
                const document = documents[0];
                const warnings = reviewSummary(document);
                return (
                  <div key={document.document_id} className="p-5">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                      <h3 className="font-semibold">
                        {isRelationship
                          ? "Möglicherweise eine gemeinsame Ausgabe"
                          : (document.facts.merchant ?? "Beleg prüfen")}{" "}
                        <span className="text-xs text-zinc-500">
                          ·{" "}
                          {isRelationship
                            ? `${documents.length} Belege`
                            : `${warnings.length} Hinweise`}
                        </span>
                      </h3>
                      <div className="flex gap-3 text-sm text-moss-700">
                        <button
                          className="focus-ring underline"
                          onClick={() =>
                            isRelationship
                              ? setComparisonIds(
                                  documents.map((d) => d.document_id),
                                )
                              : openReview(document.document_id)
                          }
                        >
                          {isRelationship
                            ? "Belege vergleichen"
                            : "Beleg prüfen"}
                        </button>
                        {!isRelationship && (
                          <button
                            className="focus-ring underline"
                            onClick={() => {
                              setEditing(true);
                              setReviewId(document.document_id);
                            }}
                          >
                            Bearbeiten
                          </button>
                        )}
                      </div>
                    </div>
                    {isRelationship && (
                      <p className="mb-3 text-sm text-zinc-600">
                        {document.facts.merchant ?? "Anbieter unbekannt"} ·{" "}
                        {new Set(
                          documents.map(
                            (d) =>
                              `${d.facts.currency}:${Number(d.facts.total)}`,
                          ),
                        ).size === 1
                          ? `${formatMoney(document.facts.total, document.facts.currency)} je Beleg`
                          : "Unterschiedliche Beträge oder Währungen"}
                        . Belege könnten dieselbe Ausgabe betreffen.
                      </p>
                    )}
                    {!isRelationship && (
                      <>
                        <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-zinc-700">
                          {warnings.map((message, index) => (
                            <li key={index}>{message}</li>
                          ))}
                        </ul>
                        <details className="mt-3 text-sm text-zinc-500">
                          <summary className="cursor-pointer">
                            Details ({document.warnings.length})
                          </summary>
                          <ul className="mt-2 list-disc space-y-1 pl-5">
                            {document.warnings
                              .filter((text) => !/^[a-z_]+:\s/.test(text))
                              .map((text, index) => (
                                <li key={index}>{text}</li>
                              ))}
                          </ul>
                        </details>
                      </>
                    )}
                    {isRelationship &&
                      documents.some((d) =>
                        d.warnings.some((w) => !duplicateWarning(w)),
                      ) && (
                        <p className="mt-2 text-xs text-amber-800">
                          Weitere Prüfpunkte werden im Vergleich angezeigt.
                        </p>
                      )}
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState icon={Check} title="Keine Auffälligkeiten" />
          )}
        </div>
      )}
    </section>
  );
}
