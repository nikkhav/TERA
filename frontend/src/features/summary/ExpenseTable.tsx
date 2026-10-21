import { formatDate, formatMoney } from "../../shared/lib/format";
import type { Summary } from "../../shared/types/domain";
import { expenseRows, type ExpenseRow } from "./groups";

function title(row: ExpenseRow) {
  const e = row.expense;
  const provider = /\b(?:uber|rasier pacific)\b/i.test(e.merchant ?? "")
    ? "Uber"
    : e.merchant;
  const description =
    e.description === e.category || e.description === "Sonstige Ausgaben"
      ? e.category === "Transport"
        ? "Fahrt"
        : "Ausgabe"
      : e.description.replace(" einschließlich Gebühren", "");
  return [provider, description].filter(Boolean).join(" · ");
}
function Amount({ row }: { row: ExpenseRow }) {
  const e = row.expense;
  const euro = e.currency === "EUR" ? e.amount : e.amount_eur;
  return (
    <div className="whitespace-nowrap text-right">
      <strong>
        {formatMoney(euro ?? e.amount, euro != null ? "EUR" : e.currency)}
      </strong>
      {e.currency !== "EUR" && (
        <span className="mt-1 block text-xs text-zinc-500">
          {euro != null
            ? formatMoney(e.amount, e.currency)
            : "EUR-Umrechnung fehlt"}
        </span>
      )}
      {row.possibleMatch && (
        <span className="block text-xs text-amber-700">je Beleg</span>
      )}
    </div>
  );
}
function status(row: ExpenseRow) {
  return row.possibleMatch
    ? "Zuordnung prüfen"
    : row.expense.status === "approved"
      ? "Bestätigt"
      : row.expense.status === "rejected"
        ? "Abgelehnt"
        : row.expense.status === "needs_review"
          ? "Prüfen"
          : "Ohne Auffälligkeiten";
}
export function ExpenseTable({
  summary,
  onReview,
  onCompare,
}: {
  summary: Summary;
  onReview: (id: string) => void;
  onCompare: (ids: string[]) => void;
}) {
  const rows = expenseRows(summary);
  const open = (row: ExpenseRow) =>
    row.possibleMatch
      ? onCompare(row.documentIds)
      : onReview(row.expense.document_id);
  return (
    <div className="@container card overflow-hidden">
      <div className="divide-y divide-line @min-[760px]:hidden">
        {rows.map((row, index) => (
          <button
            key={index}
            className="focus-ring block w-full p-4 text-left hover:bg-zinc-50"
            onClick={() => open(row)}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <span className="text-xs text-zinc-500">
                  {formatDate(row.expense.date)} · {row.expense.category}
                </span>
                <strong className="mt-1 block">{title(row)}</strong>
                <span className="mt-1 block text-xs text-zinc-500">
                  {row.documentIds.length}{" "}
                  {row.documentIds.length === 1 ? "Beleg" : "Belege"}
                </span>
              </div>
              <Amount row={row} />
            </div>
            <span
              className={`mt-3 inline-block text-xs font-semibold ${row.expense.status === "needs_review" || row.possibleMatch ? "text-amber-800" : "text-zinc-600"}`}
            >
              {status(row)} →
            </span>
          </button>
        ))}
      </div>
      <div className="hidden max-h-[65vh] overflow-auto @min-[760px]:block">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-zinc-50 text-xs text-zinc-500">
            <tr>
              {["Datum", "Ausgabe", "Kategorie", "Betrag", "Status"].map(
                (h) => (
                  <th
                    key={h}
                    className={`px-4 py-3 ${h === "Betrag" ? "text-right" : ""}`}
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row, index) => (
              <tr
                key={index}
                className="cursor-pointer hover:bg-zinc-50 focus-within:bg-zinc-50"
                onClick={() => open(row)}
              >
                <td className="whitespace-nowrap px-4 py-4 text-zinc-500">
                  {formatDate(row.expense.date)}
                </td>
                <td className="px-4 py-4">
                  <button
                    className="focus-ring text-left"
                    onClick={(event) => {
                      event.stopPropagation();
                      open(row);
                    }}
                  >
                    <strong className="block">{title(row)}</strong>
                    <span className="mt-1 block text-xs text-zinc-500">
                      {row.documentIds.length}{" "}
                      {row.documentIds.length === 1 ? "Beleg" : "Belege"} ·
                      Öffnen
                    </span>
                  </button>
                </td>
                <td className="px-4 py-4 text-zinc-600">
                  {row.expense.category}
                </td>
                <td className="px-4 py-4">
                  <Amount row={row} />
                </td>
                <td className="px-4 py-4">
                  <button
                    className={`focus-ring rounded-full px-3 py-1.5 text-xs font-semibold ${row.possibleMatch || row.expense.status === "needs_review" ? "bg-amber-50 text-amber-800" : row.expense.status === "rejected" ? "bg-red-50 text-red-700" : "bg-zinc-100 text-zinc-600"}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      open(row);
                    }}
                  >
                    {status(row)}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <p className="p-8 text-center text-sm text-zinc-500">
          Keine Ausgaben vorhanden.
        </p>
      )}
    </div>
  );
}
