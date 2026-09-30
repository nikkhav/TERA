import { formatMoney } from "../../shared/lib/format";
import type { CategoryTotal } from "../../shared/types/domain";
import { categoryIcons } from "./category";

export function CategoryCard({ row }: { row: CategoryTotal }) {
  const Icon = categoryIcons[row.category];
  return (
    <div className="rounded-2xl border border-line bg-white p-4">
      <div className="mb-4 flex items-center justify-between">
        <span className="grid size-9 place-items-center rounded-xl bg-moss-50 text-moss-700">
          <Icon size={17} />
        </span>
        <span className="text-xs font-semibold text-zinc-400">
          {row.currency ?? "–"}
        </span>
      </div>
      <p className="text-xs font-semibold text-zinc-500">{row.category}</p>
      <p className="mt-1 text-lg font-bold tracking-tight">
        {formatMoney(row.confirmed, row.currency)}
      </p>
      {row.unknown_amounts > 0 && (
        <p className="mt-1 text-xs text-amber-700">
          {row.unknown_amounts} ohne Betrag in{" "}
          {row.currency ?? "bekannter Währung"}
        </p>
      )}
      {Number(row.in_review) !== 0 && (
        <p className="mt-1 text-xs font-semibold text-amber-700">
          {formatMoney(row.in_review, row.currency)} in Prüfung
        </p>
      )}
      {Number(row.excluded || 0) !== 0 && (
        <p className="mt-1 text-xs font-semibold text-red-700">
          {formatMoney(row.excluded, row.currency)} abgelehnt
        </p>
      )}
    </div>
  );
}
