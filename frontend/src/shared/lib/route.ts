import type { ReceiptFacts } from "../types/domain";

export function receiptRoute(facts: ReceiptFacts): string {
  if (facts.category === "Flugreisen" && facts.flight_route)
    return facts.flight_route;
  if (
    facts.origin &&
    facts.destination &&
    facts.origin.toLowerCase() === facts.destination.toLowerCase()
  )
    return `Start und Ziel: ${facts.origin}`;
  return [facts.origin, facts.destination].filter(Boolean).join(" → ");
}
