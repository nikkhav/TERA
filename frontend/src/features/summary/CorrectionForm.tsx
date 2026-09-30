import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import type {
  DocumentResult,
  ExpenseCategory,
  ReceiptFacts,
  Summary,
} from "../../shared/types/domain";
import { summariesApi } from "../../shared/api/summaries";
import { errorMessage } from "../../shared/api/client";
import { Button } from "../../shared/ui/Button";

const categories: ExpenseCategory[] = [
  "Hotel",
  "Flugreisen",
  "Verpflegung",
  "Sonstige Ausgaben",
];
const fields = [
  ["merchant", "Anbieter", "text"],
  ["invoice_number", "Rechnungsnummer", "text"],
  ["invoice_date", "Rechnungsdatum / Kursdatum", "date"],
  ["currency", "Währung (ISO)", "text"],
  ["service_start", "Leistung von", "date"],
  ["service_end", "Leistung bis", "date"],
  ["total", "Gesamtbetrag", "number"],
  ["net_total", "Nettosumme", "number"],
  ["tax_total", "Steuersumme", "number"],
  ["overnight_count", "Übernachtungen", "number"],
  ["room_count", "Zimmer", "number"],
  ["transport_mode", "Verkehrsmittel", "text"],
  ["distance_km", "Entfernung (km)", "number"],
  ["origin", "Abfahrt / Abflug", "text"],
  ["destination", "Ziel", "text"],
  ["flight_number", "Flugnummer", "text"],
] as const;

export function CorrectionForm({
  document,
  summary,
  onClose,
}: {
  document: DocumentResult;
  summary: Summary;
  onClose: () => void;
}) {
  const [facts, setFacts] = useState<ReceiptFacts>(() =>
    structuredClone(document.facts),
  );
  const [comment, setComment] = useState("");
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      summariesApi.correct(
        summary.job_id,
        document.document_id,
        {
          ...facts,
          breakfast_total: null,
          breakfast_net: null,
          breakfast_tax: null,
        },
        comment,
      ),
    onSuccess: async (result) => {
      queryClient.setQueryData(["summary", summary.job_id], result);
      await queryClient.invalidateQueries({
        queryKey: ["jobs", summary.trip_id],
      });
      onClose();
    },
  });
  function changeItem(
    index: number,
    patch: Partial<ReceiptFacts["items"][number]>,
  ) {
    setFacts((previous) => ({
      ...previous,
      items: previous.items.map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    }));
  }
  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <h3 className="font-bold">Beleg korrigieren</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map(([key, label, type]) => (
          <label key={key}>
            <span className="label">{label}</span>
            <input
              className="field"
              type={type}
              step={type === "number" ? "any" : undefined}
              value={facts[key] ?? ""}
              maxLength={key === "currency" ? 3 : undefined}
              onChange={(event) => {
                const value = event.target.value;
                setFacts((previous) => ({
                  ...previous,
                  [key]:
                    value === ""
                      ? null
                      : key === "overnight_count" || key === "room_count"
                        ? Number(value)
                        : key === "currency"
                          ? value.toUpperCase()
                          : value,
                }));
              }}
            />
          </label>
        ))}
        <label>
          <span className="label">Belegkategorie</span>
          <select
            className="field"
            value={facts.category ?? ""}
            onChange={(event) =>
              setFacts({
                ...facts,
                category: event.target.value as ExpenseCategory,
              })
            }
          >
            <option value="" disabled>
              Auswählen
            </option>
            {categories.map((category) => (
              <option key={category}>{category}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="space-y-4">
        {facts.items.map((item, index) => (
          <div
            key={index}
            className="rounded-xl border border-line p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold">Position {index + 1}</h4>
              <Button
                type="button"
                variant="secondary"
                aria-label={`Position ${index + 1} entfernen`}
                onClick={() =>
                  setFacts({
                    ...facts,
                    items: facts.items.filter((_, i) => i !== index),
                  })
                }
              >
                <Trash2 size={15} />
              </Button>
            </div>
            <label className="block">
              <span className="label">Beschreibung</span>
              <input
                required
                className="field"
                value={item.description}
                onChange={(event) =>
                  changeItem(index, { description: event.target.value })
                }
              />
            </label>
            <label className="block">
              <span className="label">Kategorie</span>
              <select
                className="field"
                value={item.category ?? ""}
                onChange={(event) =>
                  changeItem(index, {
                    category: event.target.value as ExpenseCategory,
                  })
                }
              >
                <option value="" disabled>
                  Auswählen
                </option>
                {categories.map((category) => (
                  <option key={category}>{category}</option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(
                [
                  ["net", "Netto"],
                  ["tax", "Steuer"],
                  ["gross", "Betrag (brutto)"],
                ] as const
              ).map(([key, label]) => (
                <label key={key}>
                  <span className="label">{label}</span>
                  <input
                    type="number"
                    step="any"
                    className="field"
                    value={item[key] ?? ""}
                    onChange={(event) =>
                      changeItem(index, { [key]: event.target.value || null })
                    }
                  />
                </label>
              ))}
            </div>
            <label className="flex gap-2 text-sm">
              <input
                type="checkbox"
                checked={item.is_breakfast}
                onChange={(event) =>
                  changeItem(index, {
                    is_breakfast: event.target.checked,
                    ...(event.target.checked
                      ? { category: "Verpflegung" as const }
                      : {}),
                  })
                }
              />
              Frühstück
            </label>
          </div>
        ))}
        <Button
          type="button"
          variant="secondary"
          onClick={() =>
            setFacts({
              ...facts,
              items: [
                ...facts.items,
                {
                  description: "",
                  category: facts.category,
                  net: null,
                  tax: null,
                  gross: null,
                  is_breakfast: false,
                  evidence: [],
                },
              ],
            })
          }
        >
          <Plus size={16} />
          Position hinzufügen
        </Button>
      </div>
      <label className="block">
        <span className="label">Kommentar (optional)</span>
        <textarea
          className="field"
          value={comment}
          maxLength={2000}
          onChange={(event) => setComment(event.target.value)}
        />
      </label>
      {mutation.error && (
        <p role="alert" className="text-sm text-red-700">
          {errorMessage(mutation.error)}
        </p>
      )}
      <div className="sticky bottom-0 flex gap-2 border-t border-line bg-white py-4">
        <Button type="submit" disabled={mutation.isPending}>
          Speichern und bestätigen
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={mutation.isPending}
          onClick={onClose}
        >
          Abbrechen
        </Button>
      </div>
    </form>
  );
}
