export interface Line {
  id: number;
  code: string;
  name: string;
}

export interface Equipment {
  id: number;
  line_id: number;
  code: string;
  name: string;
}

export interface Reason {
  id: number;
  code: string;
  name: string;
  category: string;
  is_failure?: boolean;
}

export type EventStatus = "open" | "analyzing" | "closed";
export type ActionStatus = "open" | "doing" | "done";

export interface FiveWhy {
  id: number;
  event_id: number;
  problem_statement: string;
  why1?: string | null;
  why2?: string | null;
  why3?: string | null;
  why4?: string | null;
  why5?: string | null;
  root_cause?: string | null;
  analyst: string;
  analyzed_at: string;
  updated_at: string;
}

export interface CorrectiveAction {
  id: number;
  event_id: number;
  content: string;
  owner: string;
  due_date?: string | null;
  status: ActionStatus;
  completed_at?: string | null;
  created_at: string;
}

export interface EventListItem {
  id: number;
  event_no: string;
  line_id: number;
  equipment_id: number;
  reason_id: number;
  start_time: string;
  end_time?: string | null;
  duration_min?: number | null;
  shift: string;
  reporter: string;
  product?: string | null;
  note?: string | null;
  status: EventStatus;
  created_at: string;
  line_name: string;
  equipment_name: string;
  reason_name: string;
  reason_category: string;
  has_analysis: boolean;
  open_actions: number;
}

export interface EventDetail extends EventListItem {
  analysis: FiveWhy | null;
  actions: CorrectiveAction[];
}

export interface EventListResponse {
  total: number;
  items: EventListItem[];
}

export interface EventCreatePayload {
  line_id: number;
  equipment_id: number;
  reason_id: number;
  start_time: string;
  end_time?: string | null;
  duration_min?: number | null;
  shift: string;
  reporter: string;
  product?: string | null;
  note?: string | null;
}

export interface ParetoItem {
  reason_id: number;
  reason_name: string;
  category: string;
  count: number;
  duration_min: number;
  count_pct: number;
  cum_pct: number;
}

export interface ParetoResponse {
  total_count: number;
  total_duration_min: number;
  items: ParetoItem[];
}

export interface ReliabilityRow {
  id: number;
  code: string;
  name: string;
  line_id?: number | null;
  line_name?: string | null;
  equipment_count: number;
  failure_count: number;
  failure_downtime_min: number;
  observation_min: number;
  mttr_min: number | null;
  mtbf_min: number | null;
  availability_pct: number | null;
}

export interface ReliabilityResponse {
  dimension: "equipment" | "line";
  date_from: string;
  date_to: string;
  rows: ReliabilityRow[];
}

export const STATUS_META: Record<
  EventStatus,
  { label: string; color: string }
> = {
  open: { label: "待分析", color: "default" },
  analyzing: { label: "分析/改善中", color: "processing" },
  closed: { label: "已关闭", color: "success" },
};

export const ACTION_STATUS_META: Record<
  ActionStatus,
  { label: string; color: string }
> = {
  open: { label: "待处理", color: "default" },
  doing: { label: "进行中", color: "processing" },
  done: { label: "已完成", color: "success" },
};

// ---------- CSV 批量导入 ----------

export type ImportRowStatus = "ok" | "duplicate" | "conflict" | "error";

export interface ImportRow {
  row_no: number;
  status: ImportRowStatus;
  external_event_no?: string | null;
  errors: string[];
  data: {
    external_event_no?: string | null;
    line_code?: string;
    equipment_code?: string;
    reason_code?: string;
    start_time?: string | null;
    end_time?: string | null;
    duration_min?: number | null;
    shift?: string;
    reporter?: string;
    product?: string | null;
    note?: string | null;
  };
  event_no?: string | null;
}

export interface ImportRowListResponse {
  total: number;
  items: ImportRow[];
}

export interface ImportBatch {
  id: number;
  filename: string;
  status: "prechecked" | "committed";
  total_rows: number;
  ok_rows: number;
  duplicate_rows: number;
  conflict_rows: number;
  error_rows: number;
  imported_rows: number;
  skipped_rows: number;
  created_at: string;
  committed_at?: string | null;
  deduplicated: boolean;
}

export interface ImportConfirmResponse {
  batch: ImportBatch;
  imported: number;
  skipped: number;
}

export const IMPORT_ROW_STATUS_META: Record<
  ImportRowStatus,
  { label: string; color: string }
> = {
  ok: { label: "可导入", color: "success" },
  duplicate: { label: "重复·跳过", color: "default" },
  conflict: { label: "冲突", color: "warning" },
  error: { label: "需修正", color: "error" },
};
