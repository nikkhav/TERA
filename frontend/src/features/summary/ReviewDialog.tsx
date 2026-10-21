import { duplicateWarning, relatedGroup } from "./groups";
import { PdfLink } from "./PdfLink";
import { documentKinds, reviewSummary } from "./review";
import { Pencil } from "lucide-react";
import { CorrectionForm } from "./CorrectionForm";
import { ReceiptDetails } from "./ReceiptDetails";
import { ExchangeRateInfo } from "./ExchangeRateInfo";
import { ReceiptNotices } from "./ReceiptNotices";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { documentsApi } from "../../shared/api/documents";
import { summariesApi } from "../../shared/api/summaries";
import { errorMessage } from "../../shared/api/client";
import { saveBlob } from "../../shared/lib/download";
import { formatMoney } from "../../shared/lib/format";
import type {
  DocumentResult,
  ReviewDecision,
  Summary,
} from "../../shared/types/domain";
import { Button } from "../../shared/ui/Button";
import { Modal } from "../../shared/ui/Modal";

const decisions = {
  approved: "Bestätigt",
  rejected: "Abgelehnt",
  pending: "Zurückgesetzt",
};

export function ReviewDialog({
  summary,
  document,
  onClose,
  initiallyEditing = false,
  onOpenDocument,
  onCompare,
}: {
  summary: Summary;
  document: DocumentResult;
  onClose: () => void;
  initiallyEditing?: boolean;
  onOpenDocument: (id: string) => void;
  onCompare: () => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(initiallyEditing);
  const [comment, setComment] = useState("");
  const expenses = summary.expenses.filter(
    (expense) => expense.document_id === document.document_id,
  );
  const canApprove =
    !document.extraction_failed &&
    !document.warnings.some(duplicateWarning) &&
    expenses.length > 0 &&
    expenses.every(
      (expense) => expense.amount !== null && expense.currency !== null,
    );
  const review = useMutation({
    mutationFn: (decision: ReviewDecision) =>
      summariesApi.review(
        summary.job_id,
        document.document_id,
        decision,
        comment,
      ),
    onSuccess: async (result) => {
      queryClient.setQueryData(["summary", summary.job_id], result);
      await queryClient.invalidateQueries({
        queryKey: ["jobs", summary.trip_id],
      });
      setComment("");
    },
  });
  const download = useMutation({
    mutationFn: async () => {
      const file = await documentsApi.download({
        id: document.document_id,
        filename: document.filename,
      });
      saveBlob(file.blob, file.filename);
    },
  });
  const sources = [
    ...new Map(
      document.sources.map((source) => [
        `${source.page}:${source.block_id ?? ""}:${source.start ?? ""}:${source.end ?? ""}:${source.quote}`,
        source,
      ]),
    ).values(),
  ];
  return (
    <Modal
      title={`${document.facts.merchant ?? "Beleg"} · Prüfen`}
      onClose={onClose}
      wide
    >
      <div>
        <div className="min-w-0">
          {editing ? (
            <div className="space-y-4">
              <PdfLink
                documentId={document.document_id}
                filename={document.filename}
              />
              <CorrectionForm
                document={document}
                summary={summary}
                onClose={() => setEditing(false)}
              />
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  <Pencil size={16} />
                  Bearbeiten
                </Button>
                <Button
                  variant="secondary"
                  disabled={download.isPending}
                  onClick={() => download.mutate()}
                >
                  PDF herunterladen
                </Button>
              </div>
              <PdfLink
                documentId={document.document_id}
                filename={document.filename}
              />
              <ReceiptDetails facts={document.facts} />
              <ExchangeRateInfo rate={document.exchange_rate} />
              <div className="divide-y divide-line">
                {expenses.map((expense, index) => (
                  <div
                    key={index}
                    className="flex justify-between gap-4 py-3 text-sm"
                  >
                    <div>
                      {expense.description}
                      <span className="mt-1 block text-xs text-zinc-500">
                        {expense.category}
                      </span>
                    </div>
                    <strong className="whitespace-nowrap">
                      {formatMoney(expense.amount, expense.currency)}
                      {expense.currency !== "EUR" && (
                        <span className="mt-1 block text-xs font-normal">
                          {expense.amount_eur != null
                            ? formatMoney(expense.amount_eur, "EUR")
                            : "EUR-Umrechnung fehlt"}
                        </span>
                      )}
                    </strong>
                  </div>
                ))}
              </div>
              <p className="text-sm text-zinc-500">
                {documentKinds[document.facts.document_kind ?? "unknown"]}
              </p>
              {(document.related_document_ids?.length ?? 0) > 0 && (
                <div className="rounded-xl bg-zinc-50 p-4 text-sm">
                  <p className="font-semibold">
                    Zugehörige / möglicherweise zusammengehörige Nachweise
                  </p>
                  {relatedGroup(summary, document.document_id).length > 1 && (
                    <button
                      className="mt-2 font-semibold text-moss-700 underline"
                      onClick={onCompare}
                    >
                      Belege gemeinsam vergleichen / zuordnen
                    </button>
                  )}
                  {summary.documents
                    .filter((item) =>
                      document.related_document_ids?.includes(item.document_id),
                    )
                    .map((item) => (
                      <button
                        key={item.document_id}
                        className="mt-2 block text-left text-moss-700 underline"
                        onClick={() => onOpenDocument(item.document_id)}
                      >
                        {item.filename}
                      </button>
                    ))}
                </div>
              )}
              {document.facts.items.length > 0 && (
                <details className="rounded-xl bg-zinc-50 p-4 text-sm">
                  <summary className="cursor-pointer font-semibold">
                    Einzelpositionen und Originalbezeichnungen (
                    {document.facts.items.length})
                  </summary>
                  <div className="mt-3 divide-y divide-line">
                    {document.facts.items.map((item, index) => (
                      <div
                        key={index}
                        className="flex justify-between gap-3 py-2"
                      >
                        <div>
                          <p>{item.description}</p>
                          {document.original_texts?.items?.[index] &&
                            document.original_texts.items[index] !==
                              item.description && (
                              <p className="mt-1 text-xs text-zinc-500">
                                Original: {document.original_texts.items[index]}
                              </p>
                            )}
                        </div>
                        <strong className="whitespace-nowrap">
                          {formatMoney(item.gross, document.facts.currency)}
                        </strong>
                      </div>
                    ))}
                  </div>
                </details>
              )}
              <ReceiptNotices
                notices={(document.notices ?? []).map((message) => ({
                  message,
                  document_id: document.document_id,
                  filename: document.filename,
                }))}
              />
              {document.warnings.length > 0 && (
                <div className="rounded-xl bg-amber-50 p-4 text-sm text-amber-900">
                  <p className="mb-2 font-semibold">Automatische Prüfung</p>
                  <ul className="list-disc space-y-2 pl-4">
                    {reviewSummary(document).map((warning, index) => (
                      <li key={index}>{warning}</li>
                    ))}
                  </ul>
                  <details className="mt-3">
                    <summary className="cursor-pointer">Details</summary>
                    <ul className="mt-2 list-disc space-y-1 pl-4">
                      {document.warnings
                        .filter((text) => !/^[a-z_]+:\s/.test(text))
                        .map((text, index) => (
                          <li key={index}>{text}</li>
                        ))}
                    </ul>
                  </details>
                </div>
              )}
              {document.original_texts && (
                <details className="text-sm">
                  <summary className="cursor-pointer font-semibold">
                    Originalbezeichnungen
                  </summary>
                  <div className="mt-2 space-y-2 text-zinc-600">
                    <p>{document.original_texts.merchant}</p>
                    {[
                      ...(document.original_texts.items ?? []),
                      ...(document.original_texts.notices ?? []),
                      ...(document.original_texts.warnings ?? []),
                    ].map((text, index) => (
                      <p key={index}>{text}</p>
                    ))}
                  </div>
                </details>
              )}
              {(document.correction_history ?? []).map((event, index) => (
                <details
                  key={index}
                  className="rounded-xl bg-zinc-50 p-4 text-sm"
                >
                  <summary className="cursor-pointer font-semibold">
                    Korrigiert · {event.user_name} ·{" "}
                    {new Date(event.corrected_at).toLocaleString("de-DE")}
                  </summary>
                  <div className="mt-3 space-y-2">
                    <p>{event.comment}</p>
                    {(
                      [
                        ["Vorher", event.before],
                        ["Nachher", event.after],
                      ] as const
                    ).map(([label, facts]) => (
                      <div key={label}>
                        <strong>{label}</strong>
                        <p>
                          {facts.merchant} ·{" "}
                          {formatMoney(facts.total, facts.currency)}
                        </p>
                        {facts.items.map((item, i) => (
                          <p key={i}>
                            {item.description} ·{" "}
                            {formatMoney(item.gross, facts.currency)}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                </details>
              ))}
              {sources.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer font-semibold">
                    Textstellen im Beleg
                  </summary>
                  <div className="mt-3 max-h-60 space-y-3 overflow-auto">
                    {sources.map((source, index) => (
                      <blockquote
                        key={index}
                        className="border-l-2 border-line pl-3"
                      >
                        <p className="mb-1 text-xs text-zinc-500">
                          Seite {source.page}
                          {source.block_id &&
                            ` · Zeile ${source.block_id.split("-r").at(-1)}`}
                        </p>
                        <p className="whitespace-pre-wrap text-zinc-600">
                          {source.quote}
                        </p>
                        {source.translation && (
                          <p className="mt-1 text-moss-800">
                            Deutsch (KI-Übersetzung): {source.translation}
                          </p>
                        )}
                      </blockquote>
                    ))}
                  </div>
                </details>
              )}
              {(document.review_history ?? []).length > 0 && (
                <div className="space-y-2 rounded-xl bg-zinc-50 p-4 text-sm">
                  {document.review_history.map((event, index) => (
                    <div key={index}>
                      <p className="font-semibold">
                        {decisions[event.decision]} · {event.user_name}
                      </p>
                      <p className="text-xs text-zinc-500">
                        {new Date(event.reviewed_at).toLocaleString("de-DE")}
                      </p>
                      {event.comment && (
                        <p className="mt-1 whitespace-pre-wrap">
                          {event.comment}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <label className="block">
                <span className="label">Kommentar (optional)</span>
                <textarea
                  className="field min-h-20"
                  value={comment}
                  maxLength={2000}
                  onChange={(event) => setComment(event.target.value)}
                />
              </label>
              <p className="text-xs text-zinc-500">
                Die Entscheidung gilt für alle Ausgaben dieses Belegs.
                Abgelehnte Beträge werden nicht in die bestätigte Summe
                aufgenommen.
              </p>
              {!canApprove && (
                <p className="text-sm text-amber-800">
                  Unvollständige Auswertung: fehlende Angaben über „Bearbeiten“
                  ergänzen.
                </p>
              )}
              {(review.error || download.error) && (
                <p role="alert" className="text-sm text-red-700">
                  {errorMessage(review.error || download.error)}
                </p>
              )}
              <div className="sticky bottom-0 flex flex-wrap gap-2 border-t border-line bg-white py-4">
                <Button
                  disabled={review.isPending || !canApprove}
                  onClick={() => review.mutate("approved")}
                >
                  Geprüft und bestätigt
                </Button>
                <Button
                  variant="secondary"
                  disabled={review.isPending}
                  onClick={() => review.mutate("rejected")}
                >
                  Ablehnen
                </Button>
                {document.review_history?.length > 0 && (
                  <Button
                    variant="secondary"
                    disabled={review.isPending}
                    onClick={() => review.mutate("pending")}
                  >
                    Prüfung zurücksetzen
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
