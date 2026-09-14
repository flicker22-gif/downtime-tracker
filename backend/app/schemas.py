from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------- 基础数据 ----------


class Line(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class Equipment(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_id: int
    code: str
    name: str


class Reason(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    category: str
    is_failure: bool = False


# ---------- 5 Whys ----------


class FiveWhyBase(BaseModel):
    problem_statement: str = Field(..., min_length=1, max_length=2000)
    why1: str | None = Field(None, max_length=1000)
    why2: str | None = Field(None, max_length=1000)
    why3: str | None = Field(None, max_length=1000)
    why4: str | None = Field(None, max_length=1000)
    why5: str | None = Field(None, max_length=1000)
    root_cause: str | None = Field(None, max_length=1000)
    analyst: str = Field(..., min_length=1, max_length=32)


class FiveWhyCreate(FiveWhyBase):
    pass


class FiveWhyUpdate(FiveWhyBase):
    pass


class FiveWhyOut(FiveWhyBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    analyzed_at: datetime
    updated_at: datetime


# ---------- 改善措施 ----------


class ActionBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    owner: str = Field(..., min_length=1, max_length=32)
    due_date: datetime | None = None
    status: str = "open"


class ActionCreate(ActionBase):
    pass


class ActionUpdate(BaseModel):
    content: str | None = Field(None, max_length=1000)
    owner: str | None = Field(None, max_length=32)
    due_date: datetime | None = None
    status: str | None = None
    completed_at: datetime | None = None


class ActionOut(ActionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    completed_at: datetime | None = None
    created_at: datetime


# ---------- 停机事件 ----------


class EventCreate(BaseModel):
    line_id: int
    equipment_id: int
    reason_id: int
    start_time: datetime
    end_time: datetime | None = None
    duration_min: int | None = Field(None, ge=0)
    shift: str = Field(..., max_length=16)
    reporter: str = Field(..., min_length=1, max_length=32)
    product: str | None = Field(None, max_length=64)
    note: str | None = None

    @model_validator(mode="after")
    def _check_times(self) -> "EventCreate":
        if self.end_time and self.start_time and self.end_time < self.start_time:
            raise ValueError("停机结束时间不能早于开始时间")
        return self


class EventUpdate(BaseModel):
    reason_id: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_min: int | None = Field(None, ge=0)
    shift: str | None = None
    reporter: str | None = None
    product: str | None = None
    note: str | None = None
    status: str | None = None


class EventListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_no: str
    line_id: int
    equipment_id: int
    reason_id: int
    start_time: datetime
    end_time: datetime | None
    duration_min: int | None
    shift: str
    reporter: str
    product: str | None
    note: str | None
    status: str
    created_at: datetime
    # 冗余名称，列表直接渲染
    line_name: str = ""
    equipment_name: str = ""
    reason_name: str = ""
    reason_category: str = ""
    has_analysis: bool = False
    open_actions: int = 0


class EventDetail(EventListItem):
    analysis: FiveWhyOut | None = None
    actions: list[ActionOut] = []


class EventListResponse(BaseModel):
    total: int
    items: list[EventListItem]


# ---------- 分析统计 ----------


class ParetoItem(BaseModel):
    reason_id: int
    reason_name: str
    category: str
    count: int
    duration_min: int
    count_pct: float
    cum_pct: float


class ParetoResponse(BaseModel):
    total_count: int
    total_duration_min: int
    items: list[ParetoItem]


# ---------- 可靠性指标（MTTR / MTBF） ----------


class ReliabilityRow(BaseModel):
    id: int
    code: str
    name: str
    line_id: int | None = None       # 设备维度时所属产线
    line_name: str | None = None
    equipment_count: int = 1         # 产线维度时纳入统计的设备数
    failure_count: int               # 故障次数（仅计 is_failure 原因）
    failure_downtime_min: int        # 故障停机总时长
    observation_min: int             # 统计区间内的运行时长基数（分钟）
    mttr_min: float | None = None    # 平均修复时间
    mtbf_min: float | None = None    # 平均无故障时间
    availability_pct: float | None = None  # 可用度 %


class ReliabilityResponse(BaseModel):
    dimension: str                   # equipment | line
    date_from: datetime
    date_to: datetime
    rows: list[ReliabilityRow]


# ---------- CSV 批量导入 ----------


class ImportRowOut(BaseModel):
    row_no: int
    status: str                      # ok / duplicate / conflict / error
    external_event_no: str | None = None
    errors: list[str] = []
    data: dict = {}                  # 规范化后的行数据（展示用）
    event_no: str | None = None      # 确认导入后生成的事件编号


class ImportRowListResponse(BaseModel):
    total: int
    items: list[ImportRowOut]


class ImportBatchOut(BaseModel):
    id: int
    filename: str
    status: str                      # prechecked / committed
    total_rows: int
    ok_rows: int
    duplicate_rows: int
    conflict_rows: int
    error_rows: int
    imported_rows: int
    skipped_rows: int
    created_at: datetime
    committed_at: datetime | None = None
    deduplicated: bool = False       # 本次上传命中同内容的历史批次


class ImportConfirmResponse(BaseModel):
    batch: ImportBatchOut
    imported: int
    skipped: int
