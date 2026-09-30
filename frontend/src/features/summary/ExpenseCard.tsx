import { Check, Pencil } from "lucide-react";
import type { Expense } from "../../shared/types/domain";
import { formatDate, formatMoney } from "../../shared/lib/format";
import { ExchangeRateInfo } from "./ExchangeRateInfo";

export function ExpenseCard({
  expense,
  onReview,
  onEdit,
}: {
  expense: Expense;
  onReview: (id: string) => void;
  onEdit: (id: string) => void;
}) {
  return (
    <article className="space-y-3 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs text-zinc-500">
            {formatDate(expense.date)} · {expense.category}
          </p>
          <p className="mt-1 font-semibold">{expense.description}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-bold">
            {formatMoney(expense.amount, expense.currency)}
          </p>
          {expense.currency !== "EUR" && (
            <p className="text-sm text-zinc-500">
              {expense.amount_eur != null
                ? formatMoney(expense.amount_eur, "EUR")
                : "EUR-Umrechnung fehlt"}
            </p>
          )}
        </div>
      </div>
      <p className="text-sm text-zinc-600">{expense.merchant ?? "Unbekannt"}</p>
      <button
        className="block break-all text-left text-xs text-moss-700 underline"
        onClick={() => onReview(expense.document_id)}
      >
        {expense.filename}
      </button>
      <ExchangeRateInfo rate={expense.exchange_rate} />
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <button
          className="focus-ring inline-flex items-center gap-1.5 font-semibold text-moss-700"
          onClick={() => onReview(expense.document_id)}
        >
          <Check size={16} />
          Prüfen / bestätigen
        </button>
        <button
          className="focus-ring inline-flex items-center gap-1.5 text-zinc-600"
          onClick={() => onEdit(expense.document_id)}
        >
          <Pencil size={15} />
          Bearbeiten
        </button>
        {expense.status === "approved" && (
          <span className="text-xs text-moss-700">Manuell bestätigt</span>
        )}
        {expense.status === "rejected" && (
          <span className="text-xs text-red-700">Abgelehnt</span>
        )}
        {expense.status === "needs_review" && (
          <span className="text-xs text-amber-700">Prüfung nötig</span>
        )}
      </div>
    </article>
  );
}
