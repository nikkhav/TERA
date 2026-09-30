import type { ReceiptFacts } from "../../shared/types/domain";
import { formatDate } from "../../shared/lib/format";

export function ReceiptDetails({ facts }: { facts: ReceiptFacts }) {
  const details = [
    [
      "Leistungszeitraum",
      facts.service_start
        ? `${formatDate(facts.service_start)}${facts.service_end && facts.service_end !== facts.service_start ? ` – ${formatDate(facts.service_end)}` : ""}`
        : null,
    ],
    ["Übernachtungen", facts.overnight_count],
    ["Zimmer", facts.room_count],
    ["Verkehrsmittel", facts.transport_mode],
    [
      "Strecke",
      [facts.origin, facts.destination].filter(Boolean).join(" → ") || null,
    ],
    ["Flugnummer", facts.flight_number],
    [
      "Entfernung",
      facts.distance_km != null ? `${facts.distance_km} km` : null,
    ],
  ].filter(([, value]) => value != null);
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-2">
      {details.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-zinc-500">{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
