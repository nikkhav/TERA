import type { DocumentResult } from "../../shared/types/domain";

export const documentKinds: Record<string, string> = {
  invoice: "Rechnung",
  receipt: "Quittung / Ticket",
  payment: "Zahlungsnachweis",
  booking: "Buchungsbestätigung",
  supporting: "Ergänzende Unterlage",
  unknown: "Dokumenttyp unklar",
};

export function reviewSummary(document: DocumentResult): string[] {
  if (document.extraction_failed) {
    return [
      "Beleg konnte nicht vollständig gelesen werden. Original prüfen oder erneut auswerten.",
    ];
  }
  const warnings = document.warnings.filter(
    (text) => !/^[a-z_]+:\s/.test(text) && /[\p{L}\p{N}]/u.test(text),
  );
  const result: string[] = [];
  const add = (text: string) => {
    if (!result.includes(text)) result.push(text);
  };
  const missing = warnings.filter((text) => /Fehlend/i.test(text));
  if (missing.length)
    add(
      `Fehlende Angaben ergänzen: ${missing.map((text) => text.split(":").at(-1)?.replace(/[.]+$/, "").trim()).join(", ")}.`,
    );
  for (const warning of warnings) {
    if (/Fehlend/i.test(warning)) continue;
    if (/doppel|dieselbe Ausgabe|zusammengehörige Belege/i.test(warning)) {
      add(
        "Möglichen Doppelbeleg prüfen: zusammengehörige Nachweise öffnen und den Betrag nur einmal bestätigen.",
      );
    } else if (
      /Summe|Differenz|Nettosumme|Steuersumme/i.test(warning) &&
      /abweich|weicht|stimmt|widerspr|Differenz/i.test(warning)
    ) {
      add(warning);
    } else if (/^Rechnungsdatum .*nicht eindeutig/i.test(warning)) {
      add(
        "Belegdatum ist nicht durch eine Textstelle bestätigt. Datum im Original prüfen und bestätigen oder über „Bearbeiten“ korrigieren.",
      );
    } else if (
      /^(Währung|Gesamtbetrag|Nettosumme|Steuersumme) .*nicht eindeutig/i.test(
        warning,
      )
    ) {
      add(warning);
    } else if (
      /nachgewiesen|nachweisbar|Textbeleg|Position \d/i.test(warning)
    ) {
      add(
        "Einige Beträge oder Angaben sind nicht sicher belegt. Mit den Originalzeilen unter „Details“ abgleichen.",
      );
    } else if (/Übersetzung/i.test(warning)) {
      add(
        "Übersetzung teilweise nicht verfügbar. Die Originalbezeichnungen bleiben unter „Details“ sichtbar.",
      );
    } else if (/Fehlend|Widersprüchliche Werte/i.test(warning)) {
      add(warning);
    } else {
      add("Uneindeutige Belegangaben prüfen; Einzelheiten unter „Details“.");
    }
  }
  if (!result.length && warnings.length)
    add("Belegangaben anhand des Originals prüfen.");
  return result;
}
