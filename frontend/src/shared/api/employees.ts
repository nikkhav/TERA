import type { Employee } from "../types/domain";
import { apiClient } from "./client";
import { listAll } from "./pagination";

export const employeesApi = {
  remove: async (employeeId: string) => {
    await apiClient.delete(`/employees/${employeeId}`);
  },
  list: () => listAll<Employee>("/employees"),
  create: async (name: string) =>
    (await apiClient.post<Employee>("/employees", { name })).data,
};
