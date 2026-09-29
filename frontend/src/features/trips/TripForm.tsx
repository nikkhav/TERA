import { LoaderCircle } from "lucide-react";
import { type FormEvent, useState } from "react";
import type { TripInput } from "../../shared/api/trips";
import { Button } from "../../shared/ui/Button";

export function TripForm({
  onSave,
  onClose,
}: {
  onSave: (values: TripInput) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        starts_on: startsOn || null,
        ends_on: endsOn || null,
      });
      onClose();
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
          {saving && <LoaderCircle size={16} className="animate-spin" />}Reise
          anlegen
        </Button>
      </div>
    </form>
  );
}
