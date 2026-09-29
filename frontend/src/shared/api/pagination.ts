import { apiClient } from "./client";

const PAGE_SIZE = 500;

export async function listAll<T>(url: string): Promise<T[]> {
  const result: T[] = [];
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const page = (
      await apiClient.get<T[]>(url, {
        params: { limit: PAGE_SIZE, offset },
      })
    ).data;
    result.push(...page);
    if (page.length < PAGE_SIZE) return result;
  }
}
