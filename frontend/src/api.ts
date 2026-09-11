import axios from "axios";
import type {
  Equipment,
  EventCreatePayload,
  EventDetail,
  EventListResponse,
  EventStatus,
  FiveWhy,
  Line,
  ParetoResponse,
  Reason,
  CorrectiveAction,
  ActionStatus,
} from "./types";

const client = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

export interface EventQuery {
  line_id?: number;
  equipment_id?: number;
  reason_id?: number;
  status?: EventStatus;
  q?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export const api = {
  // 基础数据
  listLines: () => client.get<Line[]>("/lines").then((r) => r.data),
  listEquipments: (lineId?: number) =>
    client
      .get<Equipment[]>("/equipments", {
        params: lineId ? { line_id: lineId } : undefined,
      })
      .then((r) => r.data),
  listReasons: () => client.get<Reason[]>("/reasons").then((r) => r.data),

  // 事件
  listEvents: (q: EventQuery) =>
    client
      .get<EventListResponse>("/events", { params: q })
      .then((r) => r.data),
  getEvent: (id: number) =>
    client.get<EventDetail>(`/events/${id}`).then((r) => r.data),
  createEvent: (payload: EventCreatePayload) =>
    client.post<EventDetail>("/events", payload).then((r) => r.data),
  updateEvent: (
    id: number,
    payload: Partial<Pick<EventCreatePayload, "reason_id">> & {
      status?: EventStatus;
    }
  ) => client.patch<EventDetail>(`/events/${id}`, payload).then((r) => r.data),

  // 5 Whys
  saveAnalysis: (eventId: number, payload: Omit<FiveWhy, "id" | "event_id" | "analyzed_at" | "updated_at">) =>
    client
      .put<FiveWhy>(`/events/${eventId}/analysis`, payload)
      .then((r) => r.data),
  deleteAnalysis: (eventId: number) =>
    client.delete(`/events/${eventId}/analysis`),

  // 改善措施
  createAction: (
    eventId: number,
    payload: { content: string; owner: string; due_date?: string | null; status?: ActionStatus }
  ) =>
    client
      .post<CorrectiveAction>(`/events/${eventId}/actions`, payload)
      .then((r) => r.data),
  updateAction: (
    eventId: number,
    actionId: number,
    payload: Partial<{ content: string; owner: string; due_date: string | null; status: ActionStatus }>
  ) =>
    client
      .patch<CorrectiveAction>(`/events/${eventId}/actions/${actionId}`, payload)
      .then((r) => r.data),
  deleteAction: (eventId: number, actionId: number) =>
    client.delete(`/events/${eventId}/actions/${actionId}`),

  // 分析
  pareto: (params: { date_from?: string; date_to?: string; line_id?: number; top?: number }) =>
    client
      .get<ParetoResponse>("/analytics/pareto", { params })
      .then((r) => r.data),
};
