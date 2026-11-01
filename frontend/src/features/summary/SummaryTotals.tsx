import { formatMoney } from "../../shared/lib/format";
import type { Summary, Total } from "../../shared/types/domain";

function PendingAmounts({ total }: { total: Total }) {
  return (
    <>
      {Number(total.in_review) !== 0 && (
        <p className="mt-2 text-xs text-amber-700">
          {formatMoney(total.in_review, total.currency)} in Prüfung
        </p>
      )}
      {Number(total.excluded || 0) !== 0 && (
        <p className="mt-2 text-xs text-zinc-500">
          {formatMoney(total.excluded, total.currency)} abgelehnt
        </p>
      )}
      {total.unknown_amounts > 0 && (
        <p className="mt-2 text-xs text-amber-700">
          {total.unknown_amounts} ohne Betrag
        </p>
      )}
    </>
  );
}

export function SummaryTotals({ totals }: { totals: Summary["totals"] }) {
  const euro = totals.eur?.find((total) => total.currency === "EUR");
  if (!totals.by_currency.length) {
    return (
      <p className="mt-6 text-sm text-zinc-500">
        Noch keine Beträge verfügbar.
      </p>
    );
  }

  return (
    <div className="mt-6 space-y-5">
      {euro && (
        <section
          aria-label="Gesamtsumme in EUR"
          className="rounded-2xl bg-ink p-5 text-white sm:p-6"
        >
          <p className="text-sm font-semibold text-zinc-300">
            {euro.unknown_amounts > 0
              ? "Teilsumme in EUR"
              : "Gesamtsumme in EUR"}
          </p>
          <p className="mt-2 text-3xl font-bold tracking-tight">
            {formatMoney(euro.confirmed, "EUR")}
          </p>
          <p className="mt-2 text-xs leading-5 text-zinc-300">
            Berücksichtigte Ausgaben aus allen Währungen, in EUR umgerechnet.
          </p>
          {Number(euro.in_review) !== 0 && (
            <p className="mt-3 text-sm text-amber-200">
              Zusätzlich {formatMoney(euro.in_review, "EUR")} in Prüfung
            </p>
          )}
          {Number(euro.excluded || 0) !== 0 && (
            <p className="mt-2 text-xs text-zinc-300">
              {formatMoney(euro.excluded, "EUR")} abgelehnt · nicht enthalten
            </p>
          )}
          {euro.unknown_amounts > 0 && (
            <p className="mt-3 text-sm leading-6 text-amber-200">
              Unvollständiger Gesamtbetrag: Bei {euro.unknown_amounts} Ausgaben
              fehlt der Betrag oder die EUR-Umrechnung. Diese sind nicht
              enthalten.
            </p>
          )}
        </section>
      )}
      <section aria-label="Originalbeträge nach Währung">
        <h3 className="text-sm font-bold">Originalbeträge nach Währung</h3>
        <p className="mt-1 text-xs leading-5 text-zinc-500">
          Berücksichtigte Ausgaben in der jeweiligen Belegwährung, ohne
          Umrechnung.
        </p>
        <div className="mt-3 grid grid-cols-[repeat(auto-fit,minmax(min(100%,200px),1fr))] gap-3">
          {totals.by_currency.map((total) => (
            <div
              key={total.currency ?? "unknown"}
              className="rounded-2xl border border-line bg-zinc-50 p-4"
            >
              <p className="text-xs font-semibold text-zinc-500">
                {total.currency ?? "Ohne Währung"}
              </p>
              <p className="mt-2 text-xl font-bold tracking-tight">
                {formatMoney(total.confirmed, total.currency)}
              </p>
              <PendingAmounts total={total} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
