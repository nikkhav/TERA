import { formatDate, formatMoney } from "../../shared/lib/format";
import type { Expense } from "../../shared/types/domain";
import { categoryIcons } from "./category";

export function ExpenseTable({
  expenses,
  onReview,
}: {
  expenses: Expense[];
  onReview: (documentId: string) => void;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="max-h-[min(65vh,640px)] overflow-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="sticky top-0 z-10 bg-zinc-50 text-xs font-semibold text-zinc-500 shadow-[0_1px_0_0_var(--color-line)]">
            <tr>
              <th className="px-5 py-3.5">Datum</th>
              <th className="px-5 py-3.5">Anbieter</th>
              <th className="px-5 py-3.5">Beschreibung / Beleg</th>
              <th className="px-5 py-3.5">Kategorie</th>
              <th className="px-5 py-3.5 text-right">Betrag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {expenses.map((expense, index) => {
              const Icon = categoryIcons[expense.category];
              return (
                <tr
                  key={`${expense.document_id}-${index}`}
                  className="hover:bg-zinc-50/60"
                >
                  <td className="whitespace-nowrap px-5 py-4 text-zinc-600">
                    {formatDate(expense.date)}
                  </td>
                  <td className="px-5 py-4 font-semibold">
                    {expense.merchant ?? "Unbekannt"}
                  </td>
                  <td className="max-w-xs px-5 py-4 text-zinc-600">
                    <span className="line-clamp-2">{expense.description}</span>
                    <button
                      className="mt-1 text-xs text-moss-700 underline underline-offset-2"
                      onClick={() => onReview(expense.document_id)}
                    >
                      {expense.filename}
                    </button>
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-moss-50 px-2.5 py-1 text-xs font-semibold text-moss-700">
                      <Icon size={12} />
                      {expense.category}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-5 py-4 text-right font-bold">
                    {formatMoney(expense.amount, expense.currency)}
                    {expense.status === "needs_review" && (
                      <span
                        className="ml-2 text-amber-600"
                        title="Prüfung nötig"
                      >
                        •
                      </span>
                    )}
                    {expense.status === "approved" && (
                      <span className="mt-1 block text-xs font-normal text-moss-700">
                        Manuell bestätigt
                      </span>
                    )}
                    {expense.status === "rejected" && (
                      <span className="mt-1 block text-xs font-normal text-red-700">
                        Abgelehnt
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!expenses.length && (
          <div className="p-10 text-center text-sm text-zinc-500">
            Keine Ausgaben vorhanden.
          </div>
        )}
      </div>
    </div>
  );
}
