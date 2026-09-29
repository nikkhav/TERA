import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CalendarDays,
  LoaderCircle,
  Menu,
  Plus,
  RefreshCw,
  Soup,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { documentsApi } from "../shared/api/documents";
import { employeesApi } from "../shared/api/employees";
import { errorMessage } from "../shared/api/client";
import { summariesApi } from "../shared/api/summaries";
import { tripsApi, type TripInput } from "../shared/api/trips";
import { saveBlob } from "../shared/lib/download";
import { formatDate } from "../shared/lib/format";
import type { Document, Employee, Trip } from "../shared/types/domain";
import { Button } from "../shared/ui/Button";
import { Breadcrumbs } from "../shared/ui/Breadcrumbs";
import { EmptyState } from "../shared/ui/EmptyState";
import { Modal } from "../shared/ui/Modal";
import { StatusPill } from "../shared/ui/StatusPill";
import { UploadPanel } from "../features/documents/UploadPanel";
import { EmployeeForm } from "../features/employees/EmployeeForm";
import { EmployeeOverview } from "../features/employees/EmployeeOverview";
import { EmployeeSidebar } from "../features/employees/EmployeeSidebar";
import { useAuth } from "../features/auth/auth-context";
import { SummaryView } from "../features/summary/SummaryView";
import { TripForm } from "../features/trips/TripForm";
import { TripSelector } from "../features/trips/TripSelector";

export function DashboardPage() {
  const { employeeId, tripId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, logout } = useAuth();
  const [employeeModal, setEmployeeModal] = useState(false);
  const [tripModal, setTripModal] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [localError, setLocalError] = useState("");

  const employees = useQuery({
    queryKey: ["employees"],
    queryFn: employeesApi.list,
  });
  const selectedEmployee = employees.data?.find(
    (item) => item.id === employeeId,
  );
  const trips = useQuery({
    queryKey: ["trips", employeeId],
    queryFn: () => tripsApi.list(employeeId!),
    enabled: Boolean(employeeId),
  });
  const selectedTrip = trips.data?.find((item) => item.id === tripId);
  const documents = useQuery({
    queryKey: ["documents", tripId],
    queryFn: () => documentsApi.list(tripId!),
    enabled: Boolean(tripId),
  });
  const jobs = useQuery({
    queryKey: ["jobs", tripId],
    queryFn: () => summariesApi.list(tripId!),
    enabled: Boolean(tripId),
    refetchInterval: (query) => {
      const latest = query.state.data?.[0];
      return latest?.status === "queued" || latest?.status === "running"
        ? 2_000
        : false;
    },
  });
  const latestJob = jobs.data?.[0];
  const reportJob = jobs.data?.find(
    (job) => job.status === "completed" || job.status === "needs_review",
  );
  const summary = useQuery({
    queryKey: ["summary", reportJob?.id],
    queryFn: () => summariesApi.result(reportJob!.id),
    enabled: Boolean(reportJob),
  });

  const createEmployee = useMutation({
    mutationFn: employeesApi.create,
    onSuccess: (employee) => {
      queryClient.setQueryData<Employee[]>(["employees"], (current = []) => [
        ...current,
        employee,
      ]);
      navigate(`/employees/${employee.id}`);
    },
  });
  const createTrip = useMutation({
    mutationFn: (input: TripInput) => tripsApi.create(employeeId!, input),
    onSuccess: (trip) => {
      queryClient.setQueryData<Trip[]>(
        ["trips", employeeId],
        (current = []) => [...current, trip],
      );
      navigate(`/employees/${employeeId}/trips/${trip.id}`);
    },
  });
  const generate = useMutation({
    mutationFn: () => summariesApi.generate(tripId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["jobs", tripId] });
      await queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
  });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const pdfs = files.filter(
        (file) =>
          file.type === "application/pdf" ||
          file.name.toLowerCase().endsWith(".pdf"),
      );
      if (pdfs.length !== files.length)
        throw new Error("Bitte nur PDF-Dokumente auswählen.");
      for (const file of pdfs) await documentsApi.upload(tripId!, file);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["documents", tripId] }),
  });

  const queryError = [
    employees.error,
    trips.error,
    documents.error,
    jobs.error,
    summary.error,
  ].find(Boolean);
  const mutationError = [
    createEmployee.error,
    createTrip.error,
    generate.error,
    upload.error,
  ].find(Boolean);
  const visibleError =
    localError ||
    (queryError ? errorMessage(queryError) : "") ||
    (mutationError ? errorMessage(mutationError) : "");
  const clearError = () => {
    setLocalError("");
    createEmployee.reset();
    createTrip.reset();
    generate.reset();
    upload.reset();
  };
  const activeJob =
    latestJob?.status === "queued" || latestJob?.status === "running";
  const progress = latestJob?.total_chunks
    ? Math.min(
        100,
        Math.round((latestJob.completed_chunks / latestJob.total_chunks) * 100),
      )
    : 0;
  useEffect(() => {
    if (latestJob?.status === "failed") {
      console.error("[TERA summary job failed]", {
        jobId: latestJob.id,
        tripId: latestJob.trip_id,
        completedChunks: latestJob.completed_chunks,
        totalChunks: latestJob.total_chunks,
        error: latestJob.error,
      });
    }
  }, [latestJob]);
  const tripPeriod =
    selectedTrip && (selectedTrip.starts_on || selectedTrip.ends_on)
      ? `${formatDate(selectedTrip.starts_on)} – ${formatDate(selectedTrip.ends_on)}`
      : "Zeitraum nicht angegeben";
  const headerTitle = selectedEmployee?.name ?? "TERA";

  async function downloadDocument(document: Document) {
    try {
      const file = await documentsApi.download(document);
      saveBlob(file.blob, file.filename);
    } catch (error) {
      setLocalError(errorMessage(error));
    }
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <EmployeeSidebar
        employees={employees.data ?? []}
        selectedId={employeeId}
        mobileOpen={mobileNav}
        user={user!}
        onSelect={(employee) => {
          navigate(`/employees/${employee.id}`);
          setMobileNav(false);
        }}
        onCreate={() => setEmployeeModal(true)}
        onClose={() => setMobileNav(false)}
        onLogout={logout}
      />
      <main className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center border-b border-line bg-[#f7f8f4]/90 px-4 backdrop-blur-xl sm:px-7 lg:px-10">
          <div className="flex min-w-0 items-center gap-3">
            <button
              className="rounded-lg p-2 text-zinc-600 lg:hidden"
              onClick={() => setMobileNav(true)}
              aria-label="Navigation öffnen"
            >
              <Menu size={20} />
            </button>
            <p className="truncate text-sm font-bold">{headerTitle}</p>
          </div>
        </header>
        <div className="mx-auto max-w-[1500px] p-4 sm:p-7 lg:p-10">
          {visibleError && (
            <div className="mb-5 flex items-start justify-between gap-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <span className="flex gap-2">
                <AlertCircle className="mt-0.5 shrink-0" size={17} />
                {visibleError}
              </span>
              <button onClick={clearError} aria-label="Meldung schließen">
                <X size={16} />
              </button>
            </div>
          )}
          {!selectedEmployee && !employees.isLoading && (
            <EmployeeOverview
              employees={employees.data ?? []}
              onSelect={(employee) => navigate(`/employees/${employee.id}`)}
              onCreate={() => setEmployeeModal(true)}
            />
          )}
          {selectedEmployee && (
            <>
              <section className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
                <div>
                  <Breadcrumbs
                    items={[
                      { label: "Mitarbeitende", to: "/" },
                      {
                        label: selectedEmployee.name,
                        to: selectedTrip
                          ? `/employees/${selectedEmployee.id}`
                          : undefined,
                      },
                      ...(selectedTrip ? [{ label: selectedTrip.name }] : []),
                    ]}
                  />
                  <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
                    {selectedTrip?.name ?? "Reisen"}
                  </h1>
                  {selectedTrip && (
                    <p className="mt-2 flex items-center gap-2 text-sm text-zinc-500">
                      <CalendarDays size={15} />
                      {tripPeriod}
                    </p>
                  )}
                </div>
                <Button variant="secondary" onClick={() => setTripModal(true)}>
                  <Plus size={16} />
                  Neue Reise
                </Button>
              </section>
              <TripSelector
                trips={trips.data ?? []}
                selectedId={tripId}
                onSelect={(trip) =>
                  navigate(`/employees/${employeeId}/trips/${trip.id}`)
                }
                onCreate={() => setTripModal(true)}
              />
              {selectedTrip ? (
                <div className="grid items-start gap-6 xl:grid-cols-[330px_minmax(0,1fr)]">
                  <div className="space-y-5">
                    <section className="card p-5">
                      <div className="flex items-start justify-between gap-3">
                        <h2 className="font-bold">Auswertung</h2>
                        {latestJob && <StatusPill status={latestJob.status} />}
                      </div>
                      {activeJob && (
                        <div className="mt-5">
                          <div className="mb-2 flex justify-between text-xs font-semibold text-zinc-500">
                            <span>
                              {latestJob.status === "queued"
                                ? "In Warteschlange"
                                : "Verarbeitung"}
                            </span>
                            <span>
                              {latestJob.completed_chunks}/
                              {latestJob.total_chunks || "–"}
                            </span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
                            <div
                              className="relative h-full min-w-8 overflow-hidden rounded-full bg-moss-500 transition-all after:absolute after:inset-0 after:animate-pulse after:bg-white/35"
                              style={{ width: `${Math.max(progress, 8)}%` }}
                            />
                          </div>
                        </div>
                      )}
                      <Button
                        className="mt-5 w-full"
                        disabled={
                          !documents.data?.length ||
                          generate.isPending ||
                          activeJob
                        }
                        onClick={() => generate.mutate()}
                      >
                        {generate.isPending ? (
                          <LoaderCircle size={16} className="animate-spin" />
                        ) : (
                          <RefreshCw size={16} />
                        )}
                        {summary.data
                          ? "Neu auswerten"
                          : "Auswertung erstellen"}
                      </Button>
                      {!documents.data?.length && (
                        <p className="mt-2 text-center text-[11px] text-zinc-400">
                          Mindestens ein PDF erforderlich
                        </p>
                      )}
                    </section>
                    <UploadPanel
                      documents={documents.data ?? []}
                      uploading={upload.isPending}
                      onUpload={(files) => upload.mutate(files)}
                      onDownload={downloadDocument}
                    />
                  </div>
                  <div className="min-w-0">
                    {summary.data ? (
                      <SummaryView summary={summary.data} />
                    ) : latestJob?.status === "failed" ? (
                      <div className="card">
                        <EmptyState
                          icon={AlertCircle}
                          title="Auswertung fehlgeschlagen"
                          text={
                            latestJob.error ??
                            "Bitte prüfe den Worker und starte die Auswertung erneut."
                          }
                        />
                      </div>
                    ) : activeJob ? (
                      <div className="card">
                        <EmptyState
                          icon={LoaderCircle}
                          title="Auswertung wird erstellt"
                          iconClassName="animate-spin"
                        />
                      </div>
                    ) : (
                      <div className="card">
                        <EmptyState icon={Soup} title="Keine Auswertung" />
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
            </>
          )}
        </div>
      </main>
      {employeeModal && (
        <Modal
          title="Mitarbeitende hinzufügen"
          onClose={() => setEmployeeModal(false)}
        >
          <EmployeeForm
            onSave={async (name) => {
              await createEmployee.mutateAsync(name);
            }}
            onClose={() => setEmployeeModal(false)}
          />
        </Modal>
      )}
      {tripModal && (
        <Modal title="Neue Reise" onClose={() => setTripModal(false)}>
          <TripForm
            onSave={async (input) => {
              await createTrip.mutateAsync(input);
            }}
            onClose={() => setTripModal(false)}
          />
        </Modal>
      )}
    </div>
  );
}
