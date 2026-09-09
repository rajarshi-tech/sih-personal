export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  public readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach ORCA services at ${API_BASE_URL}. Check that the backend is running.`
    );
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);

    const detail =
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed (${response.status})`;

    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

/* =========================
   LOCATION
========================= */

export interface LocationInfo {
  latitude: number;
  longitude: number;
}

/* =========================
   PFZ
========================= */

export interface PFZResult {
  pfz_id: string;
  distance_km: number;
  nearest_point: LocationInfo;
  properties: Record<string, unknown>;
}

export interface NearestPFZResponse {
  user_location: LocationInfo;
  nearest_pfz: PFZResult | null;
}

/* =========================
   SAFETY
========================= */

export interface SafetyCheckResponse {
  status: string;
  data_confidence?: string;

  inside_mpa: boolean;
  mpa_areas: Array<{
    name: string;
    type: string;
  }>;

  inside_india_eez: boolean;

  distance_to_imbl_m: number | null;
  imbl_alert: boolean;

  bathymetry_available: boolean;

  is_land: boolean | null;
  elevation_m: number | null;

  depth_m: number | null;
  depth_status: string;

  warnings: string[];
}

/* =========================
   WEATHER
========================= */

export interface WeatherData {
  temp: string;
  wind: string;
  desc: string;
  waves: string;
}

/* =========================
   FULL REPORT
========================= */

export interface FullReportResponse {
  location: LocationInfo;

  nearest_pfz: PFZResult | null;

  nearest_pfzs?: PFZResult[];

  safety: SafetyCheckResponse;

  weather?: WeatherData | null;
}

/* =========================
   API FUNCTIONS
========================= */

export const getSafetyCheck = (
  lat: number,
  lon: number
) =>
  request<SafetyCheckResponse>(
    `/safety-check?latitude=${encodeURIComponent(
      lat
    )}&longitude=${encodeURIComponent(lon)}`
  );

export const getNearestPFZ = (
  lat: number,
  lon: number
) =>
  request<NearestPFZResponse>(
    `/nearest-pfz?latitude=${encodeURIComponent(
      lat
    )}&longitude=${encodeURIComponent(lon)}`
  );

export const getPFZLines = () =>
  request<any>('/pfz-lines');

export const getFullReport = (
  lat: number,
  lon: number
) =>
  request<FullReportResponse>(
    `/full-report?latitude=${encodeURIComponent(
      lat
    )}&longitude=${encodeURIComponent(lon)}`
  );

/* =========================
   CHATBOT
========================= */

export interface ChatResponse {
  session_id: string;
  reply: string;
  lang_code: string;

  audio_base64?: string;

  geo_status?: string;

  depth_m?: number | null;

  distance_to_imbl_m?: number | null;
}

export interface ChatSession {
  session_id: string;
  title: string;
}

export interface ChatHistoryEntry {
  role: 'user' | 'model';
  content: string;
}

export function chatFishery(
  message: string,
  lat: number,
  lon: number,
  sessionId?: string
) {
  const body = new FormData();

  body.append('message', message);
  body.append('lat', String(lat));
  body.append('lon', String(lon));

  if (sessionId) {
    body.append('session_id', sessionId);
  }

  return request<ChatResponse>(
    '/chat-fishery',
    {
      method: 'POST',
      body,
    }
  );
}

export const createChatSession = () =>
  request<ChatSession>(
    '/api/sessions/new',
    {
      method: 'POST',
    }
  );

export const getChatSessions = () =>
  request<ChatSession[]>('/api/sessions');

export const getChatSession = (
  sessionId: string
) =>
  request<{
    title: string;
    history: ChatHistoryEntry[];
  }>(
    `/api/sessions/${encodeURIComponent(sessionId)}`
  );

export const deleteChatSession = (
  sessionId: string
) =>
  request<{ status: string }>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'DELETE',
    }
  );

export interface RouteWaypoint {
  latitude: number;
  longitude: number;
  status: string;
}

export interface Coordinate {
  latitude: number;
  longitude: number;
}

export interface RouteResponse {
  status: string;
  distance_km: number;
  route: RouteWaypoint[];
  warnings: string[];
  start: Coordinate;
  destination: Coordinate;
}

export const getRoute = (
  startLat: number,
  startLon: number,
  endLat: number,
  endLon: number
) => {
  return request<RouteResponse>(
    "/api/navigation/route",
    {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        start: {
          latitude: startLat,
          longitude: startLon,
        },

        destination: {
          latitude: endLat,
          longitude: endLon,
        },
      }),
    }
  );
};
/* =========================
   BOUNDARIES
========================= */

export const getBoundary = (
  type: 'mpas' | 'eez' | 'imbl'
) =>
  request<unknown>(
    `/boundaries/${type}`
  );