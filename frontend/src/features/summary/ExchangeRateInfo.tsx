import type { ExchangeRate } from "../../shared/types/domain";
import { formatDate } from "../../shared/lib/format";

export function ExchangeRateInfo({ rate }: { rate?: ExchangeRate | null }) {
  if (!rate) return null;
  return (
    <p className="mt-1 text-xs font-normal text-zinc-500">
      {rate.rate
        ? `1 ${rate.currency} = ${new Intl.NumberFormat("de-DE", { maximumFractionDigits: 12 }).format(Number(rate.rate))} EUR · Kursdatum ${formatDate(rate.as_of)}`
        : rate.error}
      {" · "}
      <a
        href={rate.source_url}
        target="_blank"
        rel="noreferrer"
        className="underline"
      >
        Bankenverband
      </a>
    </p>
  );
}
