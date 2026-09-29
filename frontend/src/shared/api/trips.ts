import type { Trip } from "../types/domain";
import { apiClient } from "./client";
import { listAll } from "./pagination";

export type TripInput = Pick<Trip, "name" | "starts_on" | "ends_on">;

export const tripsApi = {
  list: (employeeId: string) => listAll<Trip>(`/employees/${employeeId}/trips`),
  create: async (employeeId: string, input: TripInput) =>
    (await apiClient.post<Trip>(`/employees/${employeeId}/trips`, input)).data,
};
