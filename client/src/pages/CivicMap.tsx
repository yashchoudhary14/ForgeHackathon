import { useEffect, useRef, useState } from "react";
import { LocateFixed } from "lucide-react";
import type { ReportOut } from "../api/civic";
import "leaflet/dist/leaflet.css";

const INDIA_CENTER: [number, number] = [25.6, 82.0];

function pinColor(status: string): { bg: string; fg: string } {
  const s = (status || "open").toLowerCase();
  if (s === "resolved" || s === "closed")
    return { bg: "#155C42", fg: "#ffffff" };
  // Darker shades keep the white count readable (4.5:1).
  if (s === "filed" || s === "in_progress")
    return { bg: "#2A5FC4", fg: "#ffffff" };
  return { bg: "#9A4A12", fg: "#ffffff" };
}

export default function CivicMap({
  reports,
  onSelect,
  onNearMe,
}: {
  reports: ReportOut[];
  onSelect?: (report: ReportOut) => void;
  onNearMe?: (lat: number, lng: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const el = containerRef.current;
    if (!el || typeof window === "undefined") return;
    void import("leaflet").then((L) => {
      if (cancelled || !containerRef.current || mapRef.current) return;
      const map = L.map(containerRef.current, {
        center: INDIA_CENTER,
        zoom: 5,
        scrollWheelZoom: false,
        zoomControl: false,
      });
      L.control.zoom({ position: "bottomright" }).addTo(map);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
      }).addTo(map);
      const group = L.layerGroup().addTo(map);
      mapRef.current = map;
      layerRef.current = group;
      renderPins(L, map, group, reports, onSelect);
    });
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const group = layerRef.current;
    if (!map || !group || typeof window === "undefined") return;
    void import("leaflet").then((L) => {
      if (!mapRef.current || !layerRef.current) return;
      renderPins(L, mapRef.current, layerRef.current, reports, onSelect);
    });
  }, [reports, onSelect]);

  function locateUser() {
    if (!navigator.geolocation) return;
    setLocating(true);
    setLocationError("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        const { latitude, longitude } = pos.coords;
        mapRef.current?.setView([latitude, longitude], 13);
        onNearMe?.(latitude, longitude);
      },
      () => {
        setLocating(false);
        setLocationError(
          "Could not read your location. Allow location access and try again.",
        );
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  return (
    <div className="relative min-h-[340px] overflow-hidden sm:min-h-[420px] rounded-[28px] bg-[#e9e3d5] shadow-[inset_0_0_0_1px_#ede5da]">
      <div
        ref={containerRef}
        aria-label="Civic issues map"
        className="z-0 h-[340px] w-full sm:h-[440px]"
      />
      <div className="pointer-events-none absolute inset-x-3.5 top-3.5 z-[400] flex flex-wrap items-center justify-between gap-2">
        <span className="rounded-full bg-white/95 px-3.5 py-2 text-xs font-semibold text-ink shadow-sm">
          OpenStreetMap ·{" "}
          {reports.filter((r) => r.lat != null && r.lng != null).length}{" "}
          geotagged reports
        </span>
        {typeof navigator !== "undefined" && !!navigator.geolocation && (
          <button
            type="button"
            disabled={locating}
            onClick={locateUser}
            className="pointer-events-auto secondary !min-h-11 !rounded-full !px-3.5 !py-1.5 text-sm shadow-sm"
          >
            <LocateFixed size={15} aria-hidden="true" />
            {locating ? "Locating…" : "Near me"}
          </button>
        )}
      </div>
      {locationError && (
        <p
          role="alert"
          className="absolute inset-x-3.5 top-32 z-[400] m-0 rounded-2xl bg-white p-3 text-sm text-bad"
        >
          {locationError}
        </p>
      )}
      <div aria-label="Map legend" className="pointer-events-none absolute bottom-16 left-3.5 z-[400] flex w-fit max-w-[calc(100%-5rem)] flex-wrap gap-3 rounded-2xl border border-line bg-white/95 px-3.5 py-2 text-xs font-semibold text-ink shadow-md backdrop-blur-md">
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#9A4A12]" />
          Open
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#2A5FC4]" />
          Filed on CPGRAMS
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-full bg-[#155C42]" />
          Resolved
        </span>
      </div>
    </div>
  );
}

function renderPins(
  L: typeof import("leaflet"),
  map: import("leaflet").Map,
  group: import("leaflet").LayerGroup,
  reports: ReportOut[],
  onSelect?: (report: ReportOut) => void,
) {
  group.clearLayers();
  const coords: [number, number][] = [];
  for (const r of reports) {
    if (typeof r.lat !== "number" || typeof r.lng !== "number") continue;
    coords.push([r.lat, r.lng]);
    const { bg, fg } = pinColor(r.status);
    const icon = L.divIcon({
      className: "civic-pin",
      html: `<div style="background:${bg};color:${fg};min-width:44px;height:44px;padding:0 8px;border-radius:999px;display:grid;place-items:center;font-weight:700;font-size:13px;border:3px solid #fff;box-shadow:0 6px 14px rgba(0,0,0,0.22);">${r.supporters}</div>`,
      iconSize: [44, 44],
      iconAnchor: [22, 22],
    });
    const marker = L.marker([r.lat, r.lng], { icon });
    marker.bindPopup(
      `<strong>${escapeHtml(r.title)}</strong><br/><small>${escapeHtml(r.department)} · Supporters: ${r.supporters}</small>`,
    );
    if (onSelect) marker.on("click", () => onSelect(r));
    marker.addTo(group);
  }
  if (coords.length === 1) {
    map.setView(coords[0], 13);
  } else if (coords.length > 1) {
    map.fitBounds(coords, { padding: [36, 36], maxZoom: 13 });
  }
}

function escapeHtml(text: string): string {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
