export type Confidence = "high" | "medium" | "low";

export interface FoodItem {
  id: string;
  name: string;
  preparation_unit: string;
  batch_size: number;
  unit_cost: number | null;
  is_active: boolean;
}

export interface SaleRow {
  id: string;
  food_item_id: string;
  food_item: string;
  sale_date: string;
  quantity_sold: number;
  prepared_quantity: number | null;
  promotion: boolean;
  stockout: boolean;
}

export interface ImportReport {
  imported: number;
  items_created: string[];
  skipped: number;
  errors: { row: number; message: string }[];
}

export interface PlanItem {
  food_item_id: string;
  food_item: string;
  preparation_unit: string;
  predicted_demand: number | null;
  recommended_preparation: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  confidence: Confidence | null;
  method: string | null;
  sample_size: number;
  last_same_weekday_sold: number | null;
  status: "ok" | "collecting_data";
  observations: number | null;
}

export interface Plan {
  target_date: string;
  model: string;
  generated_at: string;
  stale: boolean;
  insights: string[];
  items: PlanItem[];
}

export interface Dashboard {
  date: string;
  sales_quantity: number;
  waste_quantity: number;
  waste_rate: number;
  estimated_waste_cost: number | null;
  currency: string;
  series: { date: string; sold: number; wasted: number }[];
  tomorrow: {
    target_date: string;
    predicted_total: number;
    recommended_total: number;
    vs_usual_pct: number | null;
  } | null;
}

export interface AnalyticsSummary {
  start: string;
  end: string;
  sales_quantity: number;
  waste_quantity: number;
  waste_rate: number;
  estimated_waste_cost: number | null;
  currency: string;
  top_wasted: { food_item: string; quantity: number; cost: number | null }[];
  weekly_trend: { week_start: string; sold: number; wasted: number }[];
}

export interface Accuracy {
  window_days: number;
  evaluated_items: number;
  mae: number;
  wape: number;
  bias: number;
  within_band_pct: number;
  stockout_days: number;
}

export interface Me {
  user: { id: string; name: string | null; email: string; role: string };
  restaurant: {
    id: string;
    name: string;
    location: string | null;
    timezone: string;
    currency: string;
  };
}
