import { AlertCircle, LoaderCircle } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { authApi } from "../../shared/api/auth";
import { errorMessage } from "../../shared/api/client";
import { Button } from "../../shared/ui/Button";
import { useAuth } from "./auth-context";

export function AuthPage() {
  const { user, login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    authApi
      .registration()
      .then(({ enabled }) => setRegistrationEnabled(enabled))
      .catch(() => undefined);
  }, []);
  if (user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await login(email, password);
      else await register(email, name, password);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-[#f7f8f4] lg:grid-cols-[1.05fr_0.95fr]">
      <section className="hidden items-center justify-center bg-ink p-12 text-white lg:flex xl:p-16">
        <div>
          <h1 className="text-6xl font-extrabold tracking-tight xl:text-7xl">
            TERA
          </h1>
        </div>
      </section>
      <section className="flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-md">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <span className="grid size-10 place-items-center rounded-xl bg-ink text-sm font-extrabold text-white">
              T
            </span>
            <span className="font-extrabold tracking-[0.16em]">TERA</span>
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight">
            {mode === "login" ? "Anmelden" : "Konto erstellen"}
          </h2>
          {error && (
            <div className="mt-6 flex gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              <AlertCircle className="mt-0.5 shrink-0" size={16} />
              {error}
            </div>
          )}
          <form onSubmit={submit} className="mt-7 space-y-4">
            {mode === "register" && (
              <div>
                <label className="label" htmlFor="display-name">
                  Name
                </label>
                <input
                  className="field"
                  id="display-name"
                  autoComplete="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  maxLength={200}
                />
              </div>
            )}
            <div>
              <label className="label" htmlFor="email">
                E-Mail-Adresse
              </label>
              <input
                className="field"
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="password">
                Passwort
              </label>
              <input
                className="field"
                id="password"
                type="password"
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={mode === "register" ? 12 : 1}
                required
              />
              <p className="mt-1.5 text-xs text-zinc-400">
                {mode === "register" ? "Mindestens 12 Zeichen" : ""}
              </p>
            </div>
            <Button className="w-full" disabled={busy}>
              {busy && <LoaderCircle size={16} className="animate-spin" />}
              {mode === "login" ? "Anmelden" : "Konto erstellen"}
            </Button>
          </form>
          {registrationEnabled && (
            <p className="mt-6 text-center text-sm text-zinc-500">
              {mode === "login" ? "Noch kein Konto?" : "Bereits registriert?"}
              <button
                className="ml-1 font-bold text-moss-700 hover:underline"
                onClick={() => {
                  setMode(mode === "login" ? "register" : "login");
                  setError("");
                }}
              >
                {mode === "login" ? "Jetzt registrieren" : "Zur Anmeldung"}
              </button>
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
