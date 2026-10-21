import type { ReceiptFacts } from "../../shared/types/domain";
import { formatDate } from "../../shared/lib/format";

export function ReceiptDetails({ facts }: { facts: ReceiptFacts }) {
  const isHotel = facts.category === "Hotel";
  const isFlight = facts.category === "Flugreisen";
  const roundTrip =
    isFlight &&
    facts.origin &&
    facts.destination &&
    facts.origin.toLowerCase() === facts.destination.toLowerCase();
  const route =
    (isFlight && facts.flight_route) ||
    (roundTrip
      ? `Hin- und Rückflug (${facts.origin})`
      : [facts.origin, facts.destination].filter(Boolean).join(" → "));
  const details = [
    [
      "Leistungszeitraum",
      facts.service_start
        ? `${formatDate(facts.service_start)}${facts.service_end && facts.service_end !== facts.service_start ? ` – ${formatDate(facts.service_end)}` : ""}`
        : null,
    ],
    ["Übernachtungen", isHotel ? facts.overnight_count : null],
    ["Zimmer", isHotel ? facts.room_count : null],
    ["Verkehrsmittel", facts.transport_mode],
    ["Strecke", route || null],
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
