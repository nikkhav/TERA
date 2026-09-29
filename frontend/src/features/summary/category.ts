import { CircleDollarSign, Hotel, Plane, Utensils } from "lucide-react";
import type { ExpenseCategory } from "../../shared/types/domain";

export const categoryIcons: Record<ExpenseCategory, typeof Hotel> = {
  Hotel,
  Flugreisen: Plane,
  Verpflegung: Utensils,
  "Sonstige Ausgaben": CircleDollarSign,
};
