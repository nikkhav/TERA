import { AlertCircle, CheckCircle2, LoaderCircle } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "../../shared/api/auth";
import { errorMessage } from "../../shared/api/client";
import { Button } from "../../shared/ui/Button";
import { useAuth } from "./auth-context";

export function ResetPasswordPage() {
  const { logout } = useAuth();
  const [token, setToken] = useState(
    () => new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "",
  );
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    // Keep the token in memory only, not in the address bar or browser history.
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmation) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await authApi.resetPassword(token, password);
      logout();
      setToken("");
      setPassword("");
      setConfirmation("");
      setDone(true);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#f7f8f4] p-5">
      <section className="card w-full max-w-md p-6 sm:p-8">
        <p className="mb-6 text-sm font-extrabold tracking-[0.16em]">TERA</p>
        <h1 className="text-2xl font-extrabold tracking-tight">
          {done ? "Passwort geändert" : "Neues Passwort festlegen"}
        </h1>
        {done ? (
          <p
            role="status"
            className="mt-5 flex gap-2 text-sm leading-6 text-moss-700"
          >
            <CheckCircle2 size={20} className="mt-0.5 shrink-0" />
            Dein Passwort wurde gespeichert. Melde dich mit deinem neuen
            Passwort an.
          </p>
        ) : !token ? (
          <p role="alert" className="mt-5 text-sm leading-6 text-zinc-600">
            Bitte öffne den vollständigen Link, den du von der Administration
            erhalten hast. Falls du die Seite neu geladen hast, öffne den Link
            erneut.
          </p>
        ) : (
          <>
            <p className="mt-3 text-sm leading-6 text-zinc-500">
              Wähle ein Passwort mit mindestens 12 Zeichen. Nach der Änderung
              musst du dich auf allen Geräten neu anmelden.
            </p>
            {error && (
              <p
                role="alert"
                className="mt-5 flex gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-800"
              >
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                {error}
              </p>
            )}
            <form onSubmit={submit} className="mt-6 space-y-4">
              <div>
                <label className="label" htmlFor="new-password">
                  Neues Passwort
                </label>
                <input
                  id="new-password"
                  className="field"
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  required
                  disabled={busy}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="confirm-password">
                  Passwort wiederholen
                </label>
                <input
                  id="confirm-password"
                  className="field"
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={128}
                  required
                  disabled={busy}
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                />
              </div>
              <Button className="w-full" disabled={busy}>
                {busy && <LoaderCircle size={16} className="animate-spin" />}
                Passwort speichern
              </Button>
            </form>
          </>
        )}
        <Link
          to="/login"
          className="focus-ring mt-6 inline-block text-sm font-semibold text-moss-700 hover:underline"
        >
          Zur Anmeldung
        </Link>
      </section>
    </main>
  );
}
