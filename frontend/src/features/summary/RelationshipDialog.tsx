import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { summariesApi } from "../../shared/api/summaries";
import { errorMessage } from "../../shared/api/client";
import { formatDate, formatMoney } from "../../shared/lib/format";
import type { DocumentResult, Summary } from "../../shared/types/domain";
import { Button } from "../../shared/ui/Button";
import { Modal } from "../../shared/ui/Modal";
import { PdfLink } from "./PdfLink";
import { documentKinds, reviewSummary } from "./review";
import { duplicateWarning } from "./groups";

export function RelationshipDialog({
  summary,
  documents,
  onClose,
  onOpenDocument,
}: {
  summary: Summary;
  documents: DocumentResult[];
  onClose: () => void;
  onOpenDocument: (id: string) => void;
}) {
  const client = useQueryClient();
  const savedPrimary =
    documents[0].relationship_history?.at(-1)?.primary_document_id;
  const [primary, setPrimary] = useState(
    documents.some((d) => d.document_id === savedPrimary)
      ? savedPrimary!
      : (documents.find(
          (d) => !d.duplicate_of && d.facts.document_kind === "invoice",
        )?.document_id ?? documents[0].document_id),
  );
  const resolve = useMutation({
    mutationFn: (resolution: "same_expense" | "separate" | "pending") =>
      summariesApi.resolveRelationship(
        summary.job_id,
        documents.map((d) => d.document_id),
        resolution,
        primary,
      ),
    onSuccess: async (result) => {
      client.setQueryData(["summary", summary.job_id], result);
      await client.invalidateQueries({ queryKey: ["jobs", summary.trip_id] });
      onClose();
    },
  });
  const primaryDocument = documents.find((d) => d.document_id === primary)!;
  const canCombine =
    !primaryDocument.extraction_failed &&
    primaryDocument.facts.total !== null &&
    primaryDocument.facts.currency !== null;
  const last = documents[0].relationship_history?.at(-1);
  const findings = documents.flatMap((document, index) => {
    const warnings = document.warnings.filter(
      (warning) => !duplicateWarning(warning),
    );
    if (!warnings.length && !document.extraction_failed) return [];
    return [
      {
        document,
        number: index + 1,
        messages: reviewSummary({ ...document, warnings }),
      },
    ];
  });
  return (
    <Modal title="Belege gemeinsam prüfen" onClose={onClose} wide>
      <p className="mb-4 text-sm text-zinc-600">
        Gehören diese Belege zu einer gemeinsamen Ausgabe? Vergleiche Betrag,
        Datum und Fahrt. Wähle bei einer gemeinsamen Ausgabe den Beleg, dessen
        Betrag berücksichtigt werden soll.
      </p>
      {last && last.resolution !== "pending" && (
        <p className="mb-4 rounded-xl bg-moss-50 p-3 text-sm">
          Zuordnung:{" "}
          {last.resolution === "same_expense"
            ? "Eine Ausgabe, mehrere Belege"
            : "Getrennte Ausgaben"}{" "}
          · {last.user_name}
        </p>
      )}
      {findings.length > 0 && (
        <section
          aria-label="Weitere Prüfpunkte"
          className="mb-4 space-y-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900"
        >
          <h3 className="font-semibold">Weitere Prüfpunkte</h3>
          {findings.map(({ document, number, messages }) => (
            <div key={document.document_id}>
              <p className="mb-1 font-semibold">
                Beleg {number} ·{" "}
                {documentKinds[document.facts.document_kind ?? "unknown"]}
              </p>
              <ul className="list-disc space-y-1 pl-4">
                {messages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        {documents.map((d, index) => (
          <section key={d.document_id} className="flex min-w-0 flex-col gap-3">
            <label className="flex flex-1 items-start gap-3 rounded-xl border border-line p-4">
              <input
                type="radio"
                name="primary-document"
                className="mt-1"
                checked={primary === d.document_id}
                onChange={() => setPrimary(d.document_id)}
              />
              <span className="min-w-0 text-sm">
                <span className="mb-1 block text-xs text-zinc-500">
                  Beleg {index + 1}
                </span>
                <strong className="block">
                  {documentKinds[d.facts.document_kind ?? "unknown"]} ·{" "}
                  {d.facts.merchant ?? "Anbieter unbekannt"}
                </strong>
                <span className="mt-1 block">
                  {formatDate(d.facts.service_start ?? d.facts.invoice_date)} ·{" "}
                  {formatMoney(d.facts.total, d.facts.currency)}
                </span>
                {(d.facts.origin || d.facts.destination) && (
                  <span className="mt-1 block text-zinc-600">
                    {d.facts.origin ?? "?"} → {d.facts.destination ?? "?"}
                  </span>
                )}
                {d.facts.service_time && (
                  <span className="block">{d.facts.service_time} Uhr</span>
                )}
                <span className="mt-2 block text-xs text-zinc-500">
                  Betrag aus diesem Beleg verwenden
                </span>
              </span>
            </label>
            <div className="space-y-2">
              <button
                className="text-sm text-moss-700 underline"
                onClick={() => onOpenDocument(d.document_id)}
              >
                Angaben und Übersetzung prüfen / bearbeiten
              </button>
              <div>
                <PdfLink documentId={d.document_id} filename={d.filename} />
              </div>
            </div>
          </section>
        ))}
      </div>
      {resolve.error && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {errorMessage(resolve.error)}
        </p>
      )}
      <div className="sticky bottom-0 mt-5 space-y-3 border-t border-line bg-white py-4">
        <p className="text-xs text-zinc-500">
          Eine gemeinsame Ausgabe wird einmal gezählt. Weitere Belege bleiben
          als Nachweise erhalten. Andere offene Prüfpunkte bleiben bestehen.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={resolve.isPending || !canCombine}
            onClick={() => resolve.mutate("same_expense")}
          >
            Eine Ausgabe, {documents.length} Belege
          </Button>
          <Button
            variant="secondary"
            disabled={resolve.isPending}
            onClick={() => resolve.mutate("separate")}
          >
            Getrennte Ausgaben
          </Button>
          {last && last.resolution !== "pending" && (
            <Button
              variant="secondary"
              disabled={resolve.isPending}
              onClick={() => resolve.mutate("pending")}
            >
              Zuordnung zurücksetzen
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
