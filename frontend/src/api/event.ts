import request from "@/api/request";
import type { EventItem, EventListResult } from "@/types/event";

export function fetchEvents(): Promise<EventItem[]> {
  return request.get<unknown, EventItem[]>("/api/competitors/events");
}

export function fetchEventList(): Promise<EventListResult> {
  return request.get<unknown, EventListResult>("/api/events/list");
}
