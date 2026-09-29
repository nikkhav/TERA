import { LoaderCircle } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "../../shared/ui/Button";

export function EmployeeForm({
  onSave,
  onClose,
}: {
  onSave: (name: string) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onSave(name.trim());
      onClose();
    } finally {
      setSaving(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <label className="label" htmlFor="employee-name">
        Name
      </label>
      <input
        id="employee-name"
        className="field"
        autoFocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="z. B. Anna Weber"
        maxLength={200}
      />
      <div className="mt-6 flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>
          Abbrechen
        </Button>
        <Button disabled={!name.trim() || saving}>
          {saving && <LoaderCircle size={16} className="animate-spin" />}
          Hinzufügen
        </Button>
      </div>
    </form>
  );
}
