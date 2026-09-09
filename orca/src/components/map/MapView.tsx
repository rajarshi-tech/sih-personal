import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMap,
  useMapEvents,
  Polyline,
  GeoJSON,
  LayersControl,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { cn } from "@/lib/utils";

// =====================================================
// TYPES
// =====================================================

interface Location {
  lat: number;
  lon: number;
}

export interface ClickedPFZ {
  id: string;
  latitude: number;
  longitude: number;
  properties?: Record<string, unknown>;
}

// =====================================================
// USER ICON
// =====================================================

const createUserIcon = () => {
  return L.divIcon({
    className: "custom-leaflet-icon",
    html: `
      <div class="relative flex items-center justify-center w-8 h-8">
        <svg
          width="24"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          class="text-red-500 fill-red-500/20 drop-shadow-md"
        >
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
      </div>
    `,
    iconSize: [24, 32],
    iconAnchor: [12, 32],
  });
};

// =====================================================
// PFZ ICON
// =====================================================

const createPfzIcon = (isSelected: boolean = false) => {
  return L.divIcon({
    className: "custom-leaflet-icon",
    html: `
      <div class="flex flex-col items-center justify-center gap-1">
        <div
          class="
            w-5 h-5 rounded-full
            ${
              isSelected
                ? "bg-green-400 border-white ring-green-400/40 scale-125"
                : "bg-green-500/80 border-white/80 ring-green-500/20"
            }
            border-2 shadow-md ring-4
            transition-all duration-300
            ${isSelected ? "animate-pulse" : ""}
          "
        ></div>

        <span
          class="
            text-xs font-bold
            ${isSelected ? "text-foreground" : "text-foreground/70"}
            drop-shadow-md
          "
          style="text-shadow: 0px 2px 4px rgba(0,0,0,0.5);"
        >
          PFZ
        </span>
      </div>
    `,
    iconSize: [60, 40],
    iconAnchor: [30, 20],
  });
};

// =====================================================
// PROPS
// =====================================================

interface MapViewProps {
  className?: string;

  userLocation?: Location;

  clickedLocation?: Location;

  onMapClick?: (location: Location) => void;

  pfzLocations?: {
    id: string;
    location: Location;
  }[];

  selectedPfzIndex?: number;

  onPfzClick?: (index: number) => void;

  // Called when user clicks a PFZ line
  onPfzLineClick?: (pfz: ClickedPFZ) => void;

  route?: {
    latitude: number;
    longitude: number;
    status: string;
  }[];

  showMPAs?: boolean;
  showEEZ?: boolean;
  showIMBL?: boolean;

  boundariesData?: {
    mpas: any | null;
    eez: any | null;
    imbl: any | null;
  };

  // All PFZ GeoJSON lines
  pfzLines?: any | null;
}

// =====================================================
// MAP CONTROLLER
// =====================================================

function MapController({
  userLocation,
  pfzLocations,
}: {
  userLocation?: Location;

  pfzLocations?: {
    location: Location;
  }[];
}) {
  const map = useMap();

  useEffect(() => {
    if (userLocation && pfzLocations && pfzLocations.length > 0) {
      const bounds = L.latLngBounds(
        [userLocation.lat, userLocation.lon],
        [userLocation.lat, userLocation.lon],
      );

      pfzLocations.forEach((p) => {
        bounds.extend([p.location.lat, p.location.lon]);
      });

      map.fitBounds(bounds, {
        padding: [50, 50],
        maxZoom: 14,
      });
    } else if (userLocation) {
      map.setView([userLocation.lat, userLocation.lon], 11);
    } else if (pfzLocations && pfzLocations.length > 0) {
      map.setView(
        [pfzLocations[0].location.lat, pfzLocations[0].location.lon],
        11,
      );
    }
  }, [map, userLocation, pfzLocations]);

  return null;
}

// =====================================================
// ZOOM CONTROLS
// =====================================================

function CustomZoomControls() {
  const map = useMap();

  return (
    <div className="absolute top-6 right-6 flex flex-col bg-card/80 backdrop-blur-md rounded-2xl shadow-xl border border-border/50 overflow-hidden z-400 pointer-events-auto">
      <button
        type="button"
        onClick={() => map.zoomIn()}
        className="w-12 h-12 flex items-center justify-center text-foreground hover:bg-muted/50 transition-colors border-b border-border/50 cursor-pointer"
        aria-label="Zoom In"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      <button
        type="button"
        onClick={() => map.zoomOut()}
        className="w-12 h-12 flex items-center justify-center text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
        aria-label="Zoom Out"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>
    </div>
  );
}

// =====================================================
// MAP CLICK HANDLER
// =====================================================

function MapClickHandler({
  onMapClick,
}: {
  onMapClick?: (location: Location) => void;
}) {
  useMapEvents({
    click: (event) => {
      onMapClick?.({
        lat: event.latlng.lat,
        lon: event.latlng.lng,
      });
    },
  });

  return null;
}

// =====================================================
// GET REPRESENTATIVE COORDINATE FROM PFZ
// =====================================================

function getPFZCoordinate(feature: any): {
  latitude: number;
  longitude: number;
} | null {
  const geometry = feature?.geometry;

  if (!geometry) {
    return null;
  }

  // ---------------------------------------------------
  // Point
  // ---------------------------------------------------

  if (geometry.type === "Point" && Array.isArray(geometry.coordinates)) {
    return {
      longitude: geometry.coordinates[0],
      latitude: geometry.coordinates[1],
    };
  }

  // ---------------------------------------------------
  // LineString
  // ---------------------------------------------------

  if (
    geometry.type === "LineString" &&
    Array.isArray(geometry.coordinates) &&
    geometry.coordinates.length > 0
  ) {
    const middleIndex = Math.floor(geometry.coordinates.length / 2);

    const coordinate = geometry.coordinates[middleIndex];

    return {
      longitude: coordinate[0],
      latitude: coordinate[1],
    };
  }

  // ---------------------------------------------------
  // MultiLineString
  // ---------------------------------------------------

  if (
    geometry.type === "MultiLineString" &&
    Array.isArray(geometry.coordinates)
  ) {
    const firstLine = geometry.coordinates[0];

    if (Array.isArray(firstLine) && firstLine.length > 0) {
      const middleIndex = Math.floor(firstLine.length / 2);

      const coordinate = firstLine[middleIndex];

      return {
        longitude: coordinate[0],
        latitude: coordinate[1],
      };
    }
  }

  // ---------------------------------------------------
  // Polygon
  // ---------------------------------------------------

  if (
    geometry.type === "Polygon" &&
    Array.isArray(geometry.coordinates) &&
    geometry.coordinates[0]?.length > 0
  ) {
    const ring = geometry.coordinates[0];

    const middleIndex = Math.floor(ring.length / 2);

    const coordinate = ring[middleIndex];

    return {
      longitude: coordinate[0],
      latitude: coordinate[1],
    };
  }

  // ---------------------------------------------------
  // MultiPolygon
  // ---------------------------------------------------

  if (geometry.type === "MultiPolygon" && Array.isArray(geometry.coordinates)) {
    const firstPolygon = geometry.coordinates[0];

    const ring = firstPolygon?.[0];

    if (Array.isArray(ring) && ring.length > 0) {
      const middleIndex = Math.floor(ring.length / 2);

      const coordinate = ring[middleIndex];

      return {
        longitude: coordinate[0],
        latitude: coordinate[1],
      };
    }
  }

  return null;
}

// =====================================================
// MAIN MAP
// =====================================================

export function MapView({
  className,
  userLocation,
  clickedLocation,
  onMapClick,
  pfzLocations,
  onPfzClick,
  onPfzLineClick,
  selectedPfzIndex = 0,
  route,
  showMPAs = false,
  showEEZ = false,
  showIMBL = false,
  boundariesData,
  pfzLines,
}: MapViewProps) {
  const [mounted, setMounted] = useState(false);

  const [userIcon, setUserIcon] = useState<L.DivIcon | null>(null);

  const [pfzIconSelected, setPfzIconSelected] = useState<L.DivIcon | null>(
    null,
  );

  const [pfzIconNormal, setPfzIconNormal] = useState<L.DivIcon | null>(null);

  // ===================================================
  // CREATE ICONS
  // ===================================================

  useEffect(() => {
    setMounted(true);

    setUserIcon(createUserIcon());
    setPfzIconSelected(createPfzIcon(true));
    setPfzIconNormal(createPfzIcon(false));
  }, []);

  if (!mounted) {
    return null;
  }

  const defaultCenter: [number, number] = [17.6868, 83.2185];

  // ===================================================
  // WEATHER BOUNDS
  // ===================================================

  const selectedPfz = pfzLocations?.[selectedPfzIndex];

  const weatherBounds = selectedPfz
    ? L.latLngBounds(
        [selectedPfz.location.lat - 1.5, selectedPfz.location.lon - 1.5],
        [selectedPfz.location.lat + 1.5, selectedPfz.location.lon + 1.5],
      )
    : undefined;

  // ===================================================
  // RENDER
  // ===================================================

  return (
    <div className={cn("relative z-0 w-full h-full", className)}>
      <MapContainer
        center={
          userLocation ? [userLocation.lat, userLocation.lon] : defaultCenter
        }
        zoom={8}
        scrollWheelZoom={true}
        className="w-full h-full z-0"
        zoomControl={false}
      >
        {/* =================================================
            MAP LAYERS
            ================================================= */}

        <LayersControl position="topleft">
          {/* BASE MAP */}

          <LayersControl.BaseLayer checked name="Map (CartoDB)">
            <TileLayer
              attribution='&copy; <a href="https://carto.com/">CartoDB</a>'
              url={`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png?key=${
                import.meta.env.VITE_CARTO_API_KEY || ""
              }`}
            />
          </LayersControl.BaseLayer>

          {/* WEATHER */}

          <LayersControl.Overlay name="Weather Hazards (Precipitation)">
            <TileLayer
              url={`${
                import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
              }/weather-tile/precipitation_new/{z}/{x}/{y}`}
              opacity={0.65}
              bounds={weatherBounds}
            />
          </LayersControl.Overlay>

          <LayersControl.Overlay name="Wind & Storms">
            <TileLayer
              url={`${
                import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
              }/weather-tile/wind_new/{z}/{x}/{y}`}
              opacity={0.65}
              bounds={weatherBounds}
            />
          </LayersControl.Overlay>

          {/* MPA */}

          {showMPAs && boundariesData?.mpas && (
            <LayersControl.Overlay checked name="Marine Protected Areas">
              <GeoJSON
                data={boundariesData.mpas}
                style={{
                  color: "#ef4444",
                  weight: 2,
                  fillColor: "#ef4444",
                  fillOpacity: 0.2,
                }}
                onEachFeature={(feature, layer) => {
                  const name = feature.properties?.NAME;

                  layer.bindPopup(
                    name ? `MPA: ${name}` : "Marine Protected Area",
                  );
                }}
              />
            </LayersControl.Overlay>
          )}

          {/* EEZ */}

          {showEEZ && boundariesData?.eez && (
            <LayersControl.Overlay checked name="India EEZ Boundary">
              <GeoJSON
                data={boundariesData.eez}
                style={{
                  color: "#3b82f6",
                  weight: 2,
                  fillOpacity: 0,
                  dashArray: "5, 5",
                }}
                onEachFeature={(_, layer) =>
                  layer.bindPopup("India EEZ Boundary")
                }
              />
            </LayersControl.Overlay>
          )}

          {/* IMBL */}

          {showIMBL && boundariesData?.imbl && (
            <LayersControl.Overlay checked name="IMBL Boundary">
              <GeoJSON
                data={boundariesData.imbl}
                style={{
                  color: "#f59e0b",
                  weight: 3,
                  fillOpacity: 0,
                  dashArray: "10, 5",
                }}
                onEachFeature={(_, layer) =>
                  layer.bindPopup("IMBL (International Maritime Boundary Line)")
                }
              />
            </LayersControl.Overlay>
          )}
        </LayersControl>

        {/* =================================================
            MAP CONTROLLERS
            ================================================= */}

        <MapController
          userLocation={userLocation}
          pfzLocations={pfzLocations}
        />

        <MapClickHandler onMapClick={onMapClick} />

        <CustomZoomControls />

        {/* =================================================
            USER LOCATION
            ================================================= */}

        {userLocation && userIcon && (
          <Marker
            position={[userLocation.lat, userLocation.lon]}
            icon={userIcon}
          >
            <Popup>Your Location</Popup>
          </Marker>
        )}

        {/* =================================================
            CLICKED MAP LOCATION
            ================================================= */}

        {clickedLocation && (
          <Marker position={[clickedLocation.lat, clickedLocation.lon]}>
            <Popup>
              Selected location
              <br />
              {clickedLocation.lat.toFixed(5)}, {clickedLocation.lon.toFixed(5)}
            </Popup>
          </Marker>
        )}

        {/* =================================================
            PFZ MARKERS
            ================================================= */}

        {pfzLocations &&
          pfzIconSelected &&
          pfzIconNormal &&
          pfzLocations.map((pfz, index) => (
            <Marker
              key={pfz.id}
              position={[pfz.location.lat, pfz.location.lon]}
              icon={
                index === selectedPfzIndex ? pfzIconSelected : pfzIconNormal
              }
              eventHandlers={{
                click: () => onPfzClick?.(index),
              }}
            >
              <Popup>
                PFZ: {pfz.id}
                <br />
                Click to navigate here.
              </Popup>
            </Marker>
          ))}

        {/* =================================================
            NAVIGATION ROUTE
            ================================================= */}

        {route && route.length > 0 && (
          <Polyline
            positions={route.map((point) => [point.latitude, point.longitude])}
            pathOptions={{
              color: "#3b82f6",
              weight: 5,
              dashArray: "10, 10",
              opacity: 0.9,
              lineCap: "round",
            }}
          />
        )}

        {/* =================================================
            ALL PFZ LINES
            ================================================= */}

        {pfzLines && (
          <GeoJSON
            key="pfz-lines-layer"
            data={pfzLines}
            style={{
              color: "#16a34a",
              weight: 3,
              opacity: 0.85,
            }}
            onEachFeature={(feature, layer) => {
              const properties = feature.properties as Record<
                string,
                unknown
              > | null;

              // Get PFZ ID

              const pfzId = String(
                feature.id ?? properties?.pfz_id ?? properties?.id ?? "PFZ",
              );

              // Get representative coordinate

              const coordinate = getPFZCoordinate(feature);

              // Create popup text

              const label = properties
                ? Object.entries(properties)
                    .filter(
                      ([, value]) =>
                        value !== null && value !== undefined && value !== "",
                    )
                    .map(([name, value]) => `${name}: ${value}`)
                    .join("<br />")
                : "";

              // =================================================
              // POPUP
              // =================================================

              layer.bindPopup(`
                <strong>${pfzId}</strong>
                <br />
                ${label || "Potential Fishing Zone"}
                <br /><br />
                <strong>
                  Click this PFZ to navigate here.
                </strong>
              `);

              // =================================================
              // CLICK PFZ
              // =================================================

              layer.on("click", () => {
                console.log("PFZ LINE CLICKED:", pfzId, coordinate);

                if (!coordinate) {
                  console.warn("Could not determine PFZ coordinate:", feature);
                  return;
                }

                // Send clicked PFZ to NavigationPage

                onPfzLineClick?.({
                  id: pfzId,
                  latitude: coordinate.latitude,
                  longitude: coordinate.longitude,
                  properties: properties ?? undefined,
                });
              });

              // =================================================
              // HOVER EFFECT
              // =================================================

              layer.on("mouseover", () => {
                if ("setStyle" in layer) {
                  (layer as L.Path).setStyle({
                    weight: 6,
                    opacity: 1,
                  });
                }
              });

              layer.on("mouseout", () => {
                if ("setStyle" in layer) {
                  (layer as L.Path).setStyle({
                    weight: 3,
                    opacity: 0.85,
                  });
                }
              });
            }}
          />
        )}
      </MapContainer>
    </div>
  );
}
