import { Users } from "lucide-react";
import { Button } from "../../shared/ui/Button";

export function EmployeeOverview({
  hasEmployees,
  onCreate,
  onOpenNavigation,
}: {
  hasEmployees: boolean;
  onCreate: () => void;
  onOpenNavigation: () => void;
}) {
  return (
    <section className="flex min-h-[65vh] flex-col items-center justify-center px-6 text-center">
      <span className="mb-5 grid size-16 place-items-center rounded-2xl bg-moss-100 text-moss-700">
        <Users size={28} />
      </span>
      <h1 className="text-2xl font-bold tracking-tight">
        {hasEmployees ? "Mitarbeitende auswählen" : "Noch keine Mitarbeitenden"}
      </h1>
      {hasEmployees ? (
        <>
          <p className="mt-3 hidden text-sm text-zinc-500 lg:block">
            Wähle eine Person in der linken Seitenleiste aus.
          </p>
          <Button
            className="mt-5 lg:hidden"
            variant="secondary"
            onClick={onOpenNavigation}
          >
            Mitarbeitende auswählen
          </Button>
        </>
      ) : (
        <Button className="mt-5" onClick={onCreate}>
          Mitarbeitende hinzufügen
        </Button>
      )}
    </section>
  );
}
