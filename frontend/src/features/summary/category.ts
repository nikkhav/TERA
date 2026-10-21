import {
  CircleDollarSign,
  Hotel,
  Plane,
  TrainFront,
  Utensils,
} from "lucide-react";
import type { ExpenseCategory } from "../../shared/types/domain";

export const categoryIcons: Record<ExpenseCategory, typeof Hotel> = {
  Hotel,
  Flugreisen: Plane,
  Transport: TrainFront,
  Verpflegung: Utensils,
  "Sonstige Ausgaben": CircleDollarSign,
};
