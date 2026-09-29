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
}: {
  summary: Summary;
  document: DocumentResult;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [comment, setComment] = useState("");
  const expenses = summary.expenses.filter(
    (expense) => expense.document_id === document.document_id,
  );
  const canApprove =
    !document.extraction_failed &&
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
        `${source.page}:${source.quote}`,
        source,
      ]),
    ).values(),
  ];
  return (
    <Modal title={document.filename} onClose={onClose} wide>
      <div className="space-y-5">
        <Button
          variant="secondary"
          disabled={download.isPending}
          onClick={() => download.mutate()}
        >
          PDF herunterladen
        </Button>
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
              </strong>
            </div>
          ))}
        </div>
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
              {document.warnings.map((warning, index) => (
                <li key={index}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
        {sources.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer font-semibold">
              Textstellen im Beleg
            </summary>
            <div className="mt-3 max-h-60 space-y-3 overflow-auto">
              {sources.map((source, index) => (
                <blockquote key={index} className="border-l-2 border-line pl-3">
                  <p className="mb-1 text-xs text-zinc-500">
                    Seite {source.page}
                  </p>
                  <p className="whitespace-pre-wrap text-zinc-600">
                    {source.quote}
                  </p>
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
                  <p className="mt-1 whitespace-pre-wrap">{event.comment}</p>
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
          Die Entscheidung gilt für alle Ausgaben dieses Belegs. Abgelehnte
          Beträge werden nicht in die bestätigte Summe aufgenommen.
        </p>
        {!canApprove && (
          <p className="text-sm text-amber-800">
            Unvollständige Auswertung: Beleg vor dem Bestätigen erneut
            auswerten.
          </p>
        )}
        {(review.error || download.error) && (
          <p role="alert" className="text-sm text-red-700">
            {errorMessage(review.error || download.error)}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
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
    </Modal>
  );
}
