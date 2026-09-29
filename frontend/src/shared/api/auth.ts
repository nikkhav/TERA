import type { AuthResponse, User } from "../types/domain";
import { apiClient } from "./client";

export const authApi = {
  registration: async () =>
    (await apiClient.get<{ enabled: boolean }>("/auth/registration")).data,
  me: async () => (await apiClient.get<User>("/auth/me")).data,
  login: async (email: string, password: string) =>
    (await apiClient.post<AuthResponse>("/auth/login", { email, password }))
      .data,
  register: async (email: string, displayName: string, password: string) =>
    (
      await apiClient.post<AuthResponse>("/auth/register", {
        email,
        display_name: displayName,
        password,
      })
    ).data,
};
