export type Kpis = Record<string, number | null>;

export interface User { id: number; email: string; name: string; role: "admin" | "manager" | "analyst" | "viewer" }

export interface Client {
  id: number; name: string; segment: string | null; business_goal: string | null; timezone: string;
  currency: string; data_mode: "demo" | "live"; monthly_budget: string | null; target_cac: string | null;
  target_roas: string | null; gross_margin_pct: string | null; operation_level: number;
  max_budget_change_pct: string; created_at: string;
}

export interface Evidence { metric: string; value: string; benchmark: string; period: string; source: string }
export interface Decision { decision: string; comment: string | null; user: string | null; created_at: string }
export interface Check { check: string; passed: boolean; detail: string }
export interface Execution {
  id: number; mode: string; status: string; checks: Check[]; verified: boolean; error: string | null;
  before_state: { daily_budget: number } | null; after_state: { daily_budget: number } | null;
  finished_at: string | null;
}

export interface Recommendation {
  id: number; campaign_id: number | null; campaign_name: string | null; platform: string | null; agent: string;
  rule: string; title: string; problem: string; evidence: Evidence[]; probable_cause: string;
  alternatives: string[]; hypothesis: string; action_type: string;
  action_payload: { from?: number; to?: number; change_pct?: number };
  recommended_action: string; expected_impact: string; priority: "alta" | "média" | "baixa";
  priority_score: number; confidence: string; risks: string; requires_approval: boolean;
  validation_metric: string; status: string; is_demo: boolean; created_at: string; updated_at: string;
  decisions: Decision[]; executions: Execution[];
}

export interface DataQuality {
  has_data: boolean; is_demo: boolean; sources: string[]; issues: string[]; last_synced_at: string | null;
  coverage: { campaign_id: number; name: string; days_with_data: number; missing_days: number }[];
}

export interface Finance {
  real_cac: number | null; target_cac: number | null; max_sustainable_cac: number | null;
  confirmed_roas: number | null; breakeven_roas: number | null; contribution_profit: number | null;
  cac_status: string; limitations: string[];
}

export interface Analysis {
  id: number; question: string; period_start: string; period_end: string; status: string; is_demo: boolean;
  created_at: string; recommendations: Recommendation[];
  summary: { answer: string; data_quality: DataQuality; finance: Finance | null; matched_ids: number[];
             method?: string; agents?: string[] } | null;
}

export interface Dashboard {
  is_demo: boolean; has_data: boolean; currency: string;
  period: { start: string; end: string; days: number }; previous_period: { start: string; end: string };
  kpis: Kpis; previous_kpis: Kpis; changes: Record<string, number | null>;
  targets: { cac: number | null; roas: number | null };
  series: { date: string; spend: number | null; confirmed_revenue: number | null; leads: number | null;
            confirmed_sales: number | null }[];
  alerts: Recommendation[]; data_quality: DataQuality;
}

export interface CampaignRow {
  id: number; name: string; platform: string; objective: string | null; status: string;
  daily_budget: number | null; is_demo: boolean; kpis: Kpis | null;
  changes: { execution_id: number; status: string; mode: string; verified: boolean; title: string;
             before: { daily_budget: number } | null; after: { daily_budget: number } | null;
             finished_at: string | null }[];
}

export interface Agent { code: string; name: string; role: string; status: "active" | "partial" | "planned";
                         phase: number; capability: string }
export interface Integration { key: string; name: string; kind: string; status: string; phase?: number; note: string }
export interface AuditEntry { id: number; ts: string; actor: string; client_id: number | null; action: string;
                              entity_type: string | null; entity_id: number | null;
                              details: Record<string, unknown>; hash: string }
