import MaplibreGeocoder from '@maplibre/maplibre-gl-geocoder';
import React from 'react';
import '@maplibre/maplibre-gl-geocoder/dist/maplibre-gl-geocoder.css';

export async function init(): Promise<void> {
  // OSS build: EE features disabled
  // eslint-disable-next-line no-console
  console.log('[OSS] Mundi Public: running without EE features');
}

export function Provider({ children }: React.PropsWithChildren) {
  return <>{children}</>;
}

export function RequireAuth({ children }: React.PropsWithChildren) {
  return <>{children}</>;
}

export function Routes(_reactRouterDom: unknown): React.ReactNode | null {
  return null;
}

export function AccountMenu(): React.ReactNode | null {
  return null;
}

export function ScheduleCallButton(): React.ReactNode | null {
  return null;
}

export function ShareEmbedModal(_props: { isOpen: boolean; onClose: () => void; projectId?: string }): React.ReactNode | null {
  return null;
}

export function ApiKeys(): React.ReactNode | null {
  return null;
}

export async function getJwt(): Promise<string | undefined> {
  return undefined;
}

export function OptionalAuth({ children }: React.PropsWithChildren) {
  return <>{children}</>;
}

export async function fetchMaybeAuth(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  // OSS build: no auth redirect; just use fetch
  return fetch(input, init);
}

// nominatim allows limited geocoding results
export function createGeocoder(maplibregl: any) {
  const geocoderApi = {
    forwardGeocode: async (config: { query: string; limit?: number }) => {
      const features: any[] = [];
      const url = new URL('https://nominatim.openstreetmap.org/search');
      url.searchParams.set('q', config.query);
      url.searchParams.set('format', 'geojson');
      url.searchParams.set('polygon_geojson', '1');
      url.searchParams.set('addressdetails', '1');
      url.searchParams.set('limit', String(config.limit ?? 5));

      const response = await fetch(url.toString(), {
        headers: { Accept: 'application/geo+json' },
      });
      const geojson = await response.json();

      for (const feature of geojson.features || []) {
        if (!feature?.bbox || feature.bbox.length !== 4) continue;
        const [minx, miny, maxx, maxy] = feature.bbox;
        const center = [minx + (maxx - minx) / 2, miny + (maxy - miny) / 2];
        features.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: center },
          place_name: feature.properties?.display_name,
          properties: feature.properties,
          text: feature.properties?.display_name,
          place_type: ['place'],
          center,
          bbox: feature.bbox,
        });
      }
      return { features };
    },
  };

  return new MaplibreGeocoder(geocoderApi as any, {
    maplibregl,
    placeholder: 'Search places',
    marker: false,
  });
}
