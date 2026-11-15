import type {
  Accuracy,
  AnalyticsSummary,
  Dashboard,
  FoodItem,
  ImportReport,
  Me,
  Plan,
  SaleRow,
  WasteReason,
  WasteRow,
} from "../types";
import { getAccessToken } from "./supabase";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const API = `${API_BASE}/api/v1`;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API}${path}`, { ...init, headers });

  if (response.status === 401) {
    window.dispatchEvent(new Event("foodwasteos:unauthorized"));
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail[0]?.msg ?? detail;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  me: () => request<Me>("/me"),

  foodItems: () => request<FoodItem[]>("/food-items"),

  createFoodItem: (payload: {
    name: string;
    preparation_unit: string;
    batch_size: number;
    unit_cost?: number | null;
  }) =>
    request<FoodItem>("/food-items", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  sales: () => request<SaleRow[]>("/sales"),

  upsertSale: (payload: {
    food_item_id: string;
    sale_date: string;
    quantity_sold: number;
    prepared_quantity?: number | null;
    promotion?: boolean;
    stockout?: boolean;
  }) =>
    request<SaleRow>("/sales", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  waste: () => request<WasteRow[]>("/waste"),

  createWaste: (payload: {
    food_item_id: string;
    waste_date: string;
    quantity_wasted: number;
    reason: WasteReason;
    notes?: string | null;
  }) =>
    request<WasteRow>("/waste", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  importCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportReport>("/sales/import", { method: "POST", body: form });
  },

  dashboard: () => request<Dashboard>("/dashboard"),

  plan: (targetDate: string) =>
    request<Plan>(`/forecasts/plan?target_date=${encodeURIComponent(targetDate)}`),

  generatePlan: (targetDate: string, force = true) =>
    request<Plan>("/forecasts/generate", {
      method: "POST",
      body: JSON.stringify({ target_date: targetDate, force }),
    }),

  accuracy: (days = 28) => request<Accuracy>(`/forecasts/accuracy?days=${days}`),

  analytics: (days = 30) =>
    request<AnalyticsSummary>(`/analytics/summary?days=${days}`),
};
