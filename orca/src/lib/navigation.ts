const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  'http://localhost:8000'

export interface Coordinate {
  latitude: number
  longitude: number
}

export interface RoutePoint {
  latitude: number
  longitude: number
  status: string
  safety?: any
}

export interface NavigationResponse {
  status: string
  distance_km: number
  route: RoutePoint[]
  warnings: string[]
}

export async function calculateRoute(
  start: Coordinate,
  destination: Coordinate
): Promise<NavigationResponse> {

  const response = await fetch(
    `${API_BASE}/api/navigation/route`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        start,
        destination,
      }),
    }
  )

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))

    throw new Error(
      error.detail || 'Unable to calculate route'
    )
  }

  return response.json()
}