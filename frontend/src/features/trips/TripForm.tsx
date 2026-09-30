import { errorMessage } from "../../shared/api/client";
import { LoaderCircle } from "lucide-react";
import { type FormEvent, useState } from "react";
import type { TripInput } from "../../shared/api/trips";
import { Button } from "../../shared/ui/Button";

export function TripForm({
  onSave,
  onClose,
  initialValues,
}: {
  onSave: (values: TripInput) => Promise<void>;
  onClose: () => void;
  initialValues?: TripInput;
}) {
  const [name, setName] = useState(initialValues?.name ?? "");
  const [startsOn, setStartsOn] = useState(initialValues?.starts_on ?? "");
  const [endsOn, setEndsOn] = useState(initialValues?.ends_on ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setError("");
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        starts_on: startsOn || null,
        ends_on: endsOn || null,
      });
      onClose();
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label className="label" htmlFor="trip-name">
          Bezeichnung
        </label>
        <input
          id="trip-name"
          className="field"
          autoFocus
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="z. B. Kundenbesuch Hamburg"
          maxLength={200}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="trip-start">
            Von
          </label>
          <input
            id="trip-start"
            className="field"
            type="date"
            value={startsOn}
            onChange={(event) => setStartsOn(event.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="trip-end">
            Bis
          </label>
          <input
            id="trip-end"
            className="field"
            type="date"
            min={startsOn}
            value={endsOn}
            onChange={(event) => setEndsOn(event.target.value)}
          />
        </div>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onClose}>
          Abbrechen
        </Button>
        <Button
          disabled={
            !name.trim() ||
            saving ||
            (!!startsOn && !!endsOn && startsOn > endsOn)
          }
        >
          {saving && <LoaderCircle size={16} className="animate-spin" />}
          {initialValues ? "Änderungen speichern" : "Reise anlegen"}
        </Button>
      </div>
    </form>
  );
}
