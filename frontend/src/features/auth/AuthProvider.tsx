import { type ReactNode, useEffect, useState } from "react";
import { authApi } from "../../shared/api/auth";
import { tokenStore } from "../../shared/api/token";
import type { User } from "../../shared/types/domain";
import { AuthContext } from "./auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unauthorized = () => setUser(null);
    window.addEventListener("tera:unauthorized", unauthorized);
    if (!tokenStore.get()) {
      setLoading(false);
      return () =>
        window.removeEventListener("tera:unauthorized", unauthorized);
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
    return () => window.removeEventListener("tera:unauthorized", unauthorized);
  }, []);

  async function login(email: string, password: string) {
    const response = await authApi.login(email, password);
    tokenStore.set(response.access_token);
    setUser(response.user);
  }

  async function register(
    email: string,
    displayName: string,
    password: string,
  ) {
    const response = await authApi.register(email, displayName, password);
    tokenStore.set(response.access_token);
    setUser(response.user);
  }

  function logout() {
    tokenStore.clear();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
