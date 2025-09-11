// Copyright Bunting Labs, Inc. 2025

import { useQuery, useQueryClient } from '@tanstack/react-query';
import legendSymbol, { type RenderElement } from 'legend-symbol-ts';
import { BasemapControl } from './BasemapControl';

function renderTree(tree: RenderElement | null): JSX.Element | null {
  if (!tree) return null;
  return React.createElement(tree.element, tree.attributes, tree.children?.map(renderTree));
}

import { COORDINATE_SYSTEM } from '@deck.gl/core';
import { PointCloudLayer } from '@deck.gl/layers';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { LASLoader } from '@loaders.gl/las';
import { Matrix4 } from '@math.gl/core';
import { bbox } from '@turf/turf';
import { Activity, Brain, Database, MousePointerClick, Send, X, ZoomIn } from 'lucide-react';
import {
  AJAXError,
  type IControl,
  type MapGeoJSONFeature,
  type MapOptions,
  Map as MLMap,
  NavigationControl,
  ScaleControl,
} from 'maplibre-gl';
import type { ChatCompletionUserMessageParam } from 'openai/resources/chat/completions';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download } from 'react-bootstrap-icons';
import ReactMarkdown from 'react-markdown';
import { ReadyState } from 'react-use-websocket';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';
import AttributeTable from '@/components/AttributeTable';
import LayerList from '@/components/LayerList';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import VersionVisualization from '@/components/VersionVisualization';
import type { ErrorEntry, UploadingFile } from '../lib/frontend-types';
import type {
  Conversation,
  EphemeralAction,
  MapData,
  MapLayer,
  MapProject,
  MapTreeResponse,
  MessageSendRequest,
  SanitizedMessage,
} from '../lib/types';

const EMPTY_POINT_CLOUD_LAYERS: MapLayer[] = [];

// Import styles in the parent component
const KUE_MESSAGE_STYLE = `
  text-sm
  [&_table]:w-full [&_table]:border-collapse [&_table]:text-left
  [&_thead]:border-b-1 [&_thead]:border-gray-600
  [&_thead_th]:font-semibold
  [&_tbody_tr]:border-b [&_tbody_tr]:border-gray-200 last:[&_tbody_tr]:border-b-0
  [&_td]:align-top
  [&_a]:text-blue-200 [&_a]:underline
`;

const SWAP_XY = new Matrix4().set(0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1);

// Custom Export PDF Control class
class ExportPDFControl implements IControl {
  private _container: HTMLDivElement | undefined;
  private _button: HTMLButtonElement | undefined;
  private _map: MLMap | undefined;
  private _mapId: string;

  constructor(mapId: string) {
    this._mapId = mapId;
  }

  onAdd(map: MLMap): HTMLElement {
    this._map = map;
    this._container = document.createElement('div');
    this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';

    const button = document.createElement('button');
    this._button = button;
    button.className = 'maplibregl-ctrl-export-pdf';
    button.type = 'button';
    button.title = 'Export map screenshot';
    button.setAttribute('aria-label', 'Export map screenshot');

    // Create camera icon (SVG)
    button.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-camera-icon lucide-camera"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>
    `;
    button.style.border = 'none';
    button.style.background = 'transparent';
    button.style.cursor = 'pointer';
    button.style.padding = '5px';
    button.style.display = 'flex';
    button.style.alignItems = 'center';
    button.style.justifyContent = 'center';

    button.addEventListener('click', this._onClickExportPDF.bind(this));

    this._container.appendChild(button);
    return this._container;
  }

  onRemove(): void {
    if (this._container && this._container.parentNode) {
      this._container.parentNode.removeChild(this._container);
    }
  }

  private async _onClickExportPDF(): Promise<void> {
    if (!this._map || !this._button) return;

    // Store original content
    const originalContent = this._button.innerHTML;

    // Replace with spinning loader
    this._button.innerHTML = `
      <svg class="animate-spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="2">
        <circle cx="12" cy="12" r="10" stroke-opacity="0.25"/>
        <path d="M12 2a10 10 0 0 1 10 10" stroke-opacity="1"/>
      </svg>
    `;
    this._button.disabled = true;

    try {
      // Get current map bounds
      const bounds = this._map.getBounds();
      const bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;

      // Get map container dimensions and double resolution
      const container = this._map.getContainer();
      const width = container.offsetWidth * 2;
      const height = container.offsetHeight * 2;

      // Call the render API endpoint to get PNG
      const response = await fetch(`/api/maps/${this._mapId}/render.png?bbox=${bbox}&width=${width}&height=${height}`);

      if (!response.ok) {
        throw new Error('Failed to render map');
      }

      // Get the PNG blob
      const blob = await response.blob();

      // For now, just download the PNG (PDF conversion can be added later)
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `map-${this._mapId}-${new Date().toISOString().split('T')[0]}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error exporting to PDF:', error);
      alert('Failed to export map. Please try again.');
    } finally {
      // Restore original content
      this._button.innerHTML = originalContent;
      this._button.disabled = false;
    }
  }
}

interface MapLibreMapProps {
  mapId: string;
  width?: string;
  height?: string;
  className?: string;
  project: MapProject;
  mapData?: MapData | null;
  mapTree: MapTreeResponse | null;
  conversationId: number | null;
  conversations: Conversation[];
  conversationsEnabled: boolean;
  setConversationId: (conversationId: number | null) => void;
  readyState: number;
  openDropzone?: () => void;
  invalidateProjectData: () => void;
  uploadingFiles?: UploadingFile[];
  hiddenLayerIDs: string[];
  toggleLayerVisibility: (layerId: string) => void;
  mapRef: React.RefObject<MLMap | null>;
  activeActions: EphemeralAction[];
  setActiveActions: React.Dispatch<React.SetStateAction<EphemeralAction[]>>;
  zoomHistory: Array<{ bounds: [number, number, number, number] }>;
  zoomHistoryIndex: number;
  setZoomHistoryIndex: React.Dispatch<React.SetStateAction<number>>;
  addError: (message: string, shouldOverrideMessages?: boolean, sourceId?: string) => void;
  dismissError: (errorId: string) => void;
  errors: ErrorEntry[];
  invalidateMapData: () => void;
}

export default function MapLibreMap({
  mapId,
  width = '100%',
  height = '500px',
  className = '',
  project,
  mapData,
  mapTree,
  conversationId,
  conversations,
  conversationsEnabled,
  setConversationId,
  readyState,
  openDropzone,
  uploadingFiles,
  hiddenLayerIDs,
  toggleLayerVisibility,
  mapRef,
  activeActions,
  setActiveActions,
  zoomHistory,
  zoomHistoryIndex,
  setZoomHistoryIndex,
  addError,
  dismissError,
  errors,
  invalidateProjectData,
  invalidateMapData,
}: MapLibreMapProps) {
  const queryClient = useQueryClient();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const localMapRef = useRef<MLMap | null>(null);
  const basemapControlRef = useRef<BasemapControl | null>(null);
  const exportPDFControlRef = useRef<ExportPDFControl | null>(null);
  const deckOverlayRef = useRef<MapboxOverlay | null>(null);
  const [hasZoomed, setHasZoomed] = useState(false);
  const [layerSymbols, setLayerSymbols] = useState<{
    [layerId: string]: JSX.Element;
  }>({});
  const { data: basemapsData } = useQuery({
    queryKey: ['basemaps', 'available'],
    queryFn: async () => {
      const response = await fetch('/api/basemaps/available');
      if (!response.ok) {
        throw new Error('Failed to fetch basemaps');
      }
      return (await response.json()) as { styles: string[]; display_names?: Record<string, string> };
    },
  });
  const availableBasemaps = basemapsData?.styles ?? [];
  const basemapDisplayNames = basemapsData?.display_names ?? {};

  const { data: demoConfigData } = useQuery({
    queryKey: ['projects', 'config', 'demo-postgis-available'],
    queryFn: async () => {
      const response = await fetch('/api/projects/config/demo-postgis-available');
      if (!response.ok) {
        throw new Error('Failed to fetch demo config');
      }
      return (await response.json()) as { available: boolean; description: string };
    },
  });
  const demoConfig = demoConfigData ?? { available: false, description: '' };

  const pointCloudLayers = useMemo(() => {
    const filtered = mapData?.layers?.filter((layer) => layer.type === 'point_cloud') ?? EMPTY_POINT_CLOUD_LAYERS;
    return filtered.length === 0 ? EMPTY_POINT_CLOUD_LAYERS : filtered;
  }, [mapData?.layers]);

  const createPointCloudLayer = useCallback((pclayer: MapLayer) => {
    // some projection-foo to compensate for web mercator (gross!) and
    // latitude-longitude disagreements (SWAP_XY)
    const { lon, lat } = pclayer.metadata?.pointcloud_anchor as { lon: number; lat: number };
    if (!lon || !lat) {
      console.error('no anchor', pclayer);
      return;
    }
    const R = 6378137;
    const d2r = Math.PI / 180;
    const cosA = Math.cos(lat * d2r);

    const mPerDegLon = R * d2r * cosA;
    const mPerDegLat = R * d2r;
    const translate = new Matrix4().translate([-lon, -lat, 0]);
    const scale = new Matrix4().scale([mPerDegLon, mPerDegLat, 1]);
    const modelMatrix = scale.multiplyRight(translate).multiplyRight(SWAP_XY);

    const layer = new PointCloudLayer({
      id: `point-cloud-layer-${pclayer.id}`,
      data: `/api/layer/${pclayer.id}.laz`,
      loaders: [LASLoader],
      loadOptions: {
        las: {
          fp64: true,
        },
      },
      modelMatrix: modelMatrix,
      coordinateSystem: COORDINATE_SYSTEM.METER_OFFSETS,
      coordinateOrigin: [lon, lat, 0],
      getColor: (_d, dinfo) => {
        const mesh = (dinfo.data as any).loaderData;

        if (!mesh.maxs || !mesh.mins) {
          return [100, 100, 255, 255];
        }

        // TODO: improve this. its a fast percentile approximation
        // but life can always be better. pastures are greener
        const pointData = dinfo.data as any;
        const currentZ = pointData.attributes.POSITION.value[dinfo.index * 3 + 2];

        if (!mesh.percentileCache) {
          const numPoints = pointData.attributes.POSITION.value.length / 3;
          const sampleSize = Math.min(5000, numPoints);
          const zValues = [];

          for (let i = 0; i < sampleSize; i++) {
            const idx = Math.floor((i / sampleSize) * numPoints) * 3 + 2;
            zValues.push(pointData.attributes.POSITION.value[idx]);
          }

          zValues.sort((a, b) => a - b);
          mesh.percentileCache = {
            p5: zValues[Math.floor(sampleSize * 0.05)],
            p95: zValues[Math.floor(sampleSize * 0.95)],
          };
        }

        const { p5, p95 } = mesh.percentileCache;
        const range = p95 - p5;

        if (range === 0) {
          return [100, 100, 255, 255];
        }

        const clampedZ = Math.max(p5, Math.min(p95, currentZ));
        const normalizedZ = (clampedZ - p5) / range;

        // TODO: interpolate between two pretty colors
        const r = Math.round(normalizedZ * 255);
        const g = Math.round(normalizedZ * 255);
        const b = Math.round((1 - normalizedZ) * 255);
        return [r, g, b, 255];
      },
      pointSize: 1,
      onError: (error: any) => {
        console.error('Point cloud loading error: ' + error.message);
      },
    });
    return layer;
  }, []);

  const [showAttributeTable, setShowAttributeTable] = useState(false);
  const [selectedLayer, setSelectedLayer] = useState<MapLayer | null>(null);

  const [isCancelling, setIsCancelling] = useState(false);

  // Function to handle basemap changes
  const handleBasemapChange = useCallback(
    async (newBasemap: string) => {
      // Parse map ID from URL, but handle case where versionIdParam is optional
      const pathParts = window.location.pathname.split('/');
      const urlMapId = pathParts.length > 3 ? pathParts[3] : mapId; // Use mapId fallback if no version in URL

      try {
        const response = await fetch(`/api/maps/${urlMapId}`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ basemap: newBasemap }),
        });

        if (response.ok) {
          // Invalidate style query to trigger immediate re-fetch with new basemap
          await queryClient.invalidateQueries({
            queryKey: ['mapStyle', urlMapId],
          });
        } else {
          console.error('Failed to update basemap:', await response.text());
        }
      } catch (error) {
        console.error('Error updating basemap:', error);
      }
    },
    [queryClient, mapId],
  );

  // Function to get the appropriate icon for an action
  const getActionIcon = (action: string) => {
    if (action.includes('thinking')) {
      return <Brain className="animate-pulse w-4 h-4 mr-2" />;
    } else if (action.includes('Downloading data from OpenStreetMap')) {
      return <Download className="animate-pulse w-4 h-4 mr-2" />;
    } else if (action.includes('SQL')) {
      return <Database className="animate-pulse w-4 h-4 mr-2" />;
    } else if (action.includes('Sending message')) {
      return <Send className="animate-pulse w-4 h-4 mr-2" />;
    } else {
      return <Activity className="w-4 h-4 mr-2 animate-pulse" />;
    }
  };

  // State for changelog entries
  // State for changelog entries from map data
  const [__changelog, setChangelog] = useState<
    Array<{
      summary: string;
      timestamp: string;
      mapState: string;
    }>
  >([]);

  // Process changelog data when mapData changes
  useEffect(() => {
    if (mapData?.changelog) {
      const formattedChangelog = mapData.changelog.map((entry) => ({
        summary: entry.message,
        timestamp: new Date(entry.last_edited).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
        mapState: entry.map_state,
      }));
      setChangelog(formattedChangelog);
    }
  }, [mapData]);

  useEffect(() => {
    if (isCancelling) {
      const cancelActions = async () => {
        await fetch(`/api/maps/${mapId}/messages/cancel`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({}),
        });

        toast.success('Actions cancelled');
        setIsCancelling(false);
      };

      cancelActions();
    }
  }, [isCancelling, mapId]);

  const [selectedFeature, setSelectedFeature] = useState<MapGeoJSONFeature | null>(null);

  const selectFeature = useCallback(
    (feat: MapGeoJSONFeature | null) => {
      if (!mapRef.current) return;
      const newMap = mapRef.current;

      setSelectedFeature((prev: MapGeoJSONFeature | null) => {
        if (prev) {
          newMap.setFeatureState({ source: prev.source, sourceLayer: prev.sourceLayer, id: prev.id }, { selected: false });
        }

        if (feat) {
          newMap.setFeatureState({ source: feat.source, sourceLayer: feat.sourceLayer, id: feat.id }, { selected: true });
        }

        return feat;
      });
    },
    [mapRef],
  );

  const UPDATE_KUE_POINTER_MSEC = 40;
  const KUE_CURVE_DURATION_MS = 2000;

  // State for Kue's animated positions (indexed by action_id)
  const [kuePositions, setKuePositions] = useState<Record<string, { lng: number; lat: number }>>({});
  const [kueTargetPoints, setKueTargetPoints] = useState<Record<string, Array<{ lng: number; lat: number }>>>({});

  // Generate random points within layer bounds
  const generateRandomPointsInBounds = useCallback((bounds: number[], count: number = 3) => {
    const [minLng, minLat, maxLng, maxLat] = bounds;
    const points = [];

    for (let i = 0; i < count; i++) {
      points.push({
        lng: minLng + Math.random() * (maxLng - minLng),
        lat: minLat + Math.random() * (maxLat - minLat),
      });
    }

    return points;
  }, []);

  // Quadratic Bezier curve interpolation from p0 to p2 through p1
  const bezierInterpolate = useCallback(
    (p0: { lng: number; lat: number }, p1: { lng: number; lat: number }, p2: { lng: number; lat: number }, t: number) => {
      const invT = 1 - t;
      return {
        lng: invT * invT * p0.lng + 2 * invT * t * p1.lng + t * t * p2.lng,
        lat: invT * invT * p0.lat + 2 * invT * t * p1.lat + t * t * p2.lat,
      };
    },
    [],
  );

  // Update Kue's target points when active actions change
  useEffect(() => {
    const activeLayerActions = activeActions.filter((action) => action.status === 'active' && action.layer_id);

    // Get current action IDs
    const currentActionIds = new Set(activeLayerActions.map((action) => action.action_id));

    // Remove state for actions that are no longer active
    setKuePositions((prev) => {
      const filtered = Object.fromEntries(Object.entries(prev).filter(([actionId]) => currentActionIds.has(actionId)));
      return filtered;
    });
    setKueTargetPoints((prev) => {
      const filtered = Object.fromEntries(Object.entries(prev).filter(([actionId]) => currentActionIds.has(actionId)));
      return filtered;
    });

    // Add state for new actions
    if (mapData?.layers) {
      activeLayerActions.forEach((action) => {
        const layer = mapData.layers.find((l) => l.id === action.layer_id);
        if (layer?.bounds && layer.bounds.length >= 4) {
          const actionId = action.action_id;

          // Only initialize if not already present
          setKueTargetPoints((prev) => {
            if (prev[actionId]) return prev;
            const newTargetPoints = generateRandomPointsInBounds(layer.bounds!);
            return { ...prev, [actionId]: newTargetPoints };
          });

          setKuePositions((prev) => {
            if (prev[actionId]) return prev;
            const newTargetPoints = generateRandomPointsInBounds(layer.bounds!);
            return { ...prev, [actionId]: newTargetPoints[0] };
          });
        }
      });
    }
  }, [activeActions, mapData, generateRandomPointsInBounds]);

  // Animate Kue's positions based on timestamp
  useEffect(() => {
    const activeActionIds = Object.keys(kueTargetPoints);
    if (activeActionIds.length === 0) return;

    const interval = setInterval(() => {
      const now = Date.now();

      activeActionIds.forEach((actionId) => {
        const targetPoints = kueTargetPoints[actionId];

        if (targetPoints && targetPoints.length >= 2) {
          // Calculate progress based on timestamp modulo curve duration
          const progress = (now % KUE_CURVE_DURATION_MS) / KUE_CURVE_DURATION_MS;

          // Check if we've started a new curve cycle
          const currentCycle = Math.floor(now / KUE_CURVE_DURATION_MS);
          const lastCycle = Math.floor((now - UPDATE_KUE_POINTER_MSEC) / KUE_CURVE_DURATION_MS);

          if (currentCycle !== lastCycle) {
            // Generate new random points for the new curve
            const layer = mapData?.layers?.find((l) => activeActions.find((a) => a.action_id === actionId)?.layer_id === l.id);
            if (layer?.bounds) {
              const newTargetPoints = generateRandomPointsInBounds(layer.bounds);
              setKueTargetPoints((prev) => ({
                ...prev,
                [actionId]: newTargetPoints,
              }));
              return; // Skip position update this frame to use new points next frame
            }
          }

          const startPoint = targetPoints[0];
          const middlePoint = targetPoints[1];
          const endPoint = targetPoints[2];

          const interpolatedPosition = bezierInterpolate(startPoint, middlePoint, endPoint, progress);

          setKuePositions((prev) => ({
            ...prev,
            [actionId]: interpolatedPosition,
          }));
        }
      });
    }, UPDATE_KUE_POINTER_MSEC);

    return () => clearInterval(interval);
  }, [kueTargetPoints, activeActions, mapData, bezierInterpolate, generateRandomPointsInBounds]);

  // Generate GeoJSON from pointer positions
  const pointsGeoJSON = useMemo(() => {
    const features: GeoJSON.Feature[] = [];

    // Add Kue's animated positions
    Object.entries(kuePositions).forEach(([actionId, position]) => {
      features.push({
        type: 'Feature' as const,
        geometry: {
          type: 'Point' as const,
          coordinates: [position.lng, position.lat],
        },
        properties: { user: 'Kue', abbrev: 'Kue', color: '#ff69b4', actionId },
      });
    });

    return {
      type: 'FeatureCollection' as const,
      features,
    };
  }, [kuePositions]);

  const loadLegendSymbols = useCallback(
    (map: MLMap) => {
      const style = map.getStyle();

      // Check if style and style.layers exist before proceeding
      if (!style || !style.layers) return;

      mapData?.layers.forEach((layer) => {
        const layerId = layer.id;

        const mapLayer = style.layers.find((styleLayer) => 'source' in styleLayer && (styleLayer as any).source === layerId);

        if (mapLayer) {
          const tree: RenderElement | null = legendSymbol({
            sprite: style.sprite,
            zoom: map.getZoom(),
            layer: mapLayer as any,
          });
          // long lasting bug
          if (tree?.attributes?.style?.backgroundImage === 'url(null)') {
            tree.attributes.style.backgroundImage = 'none';
            tree.attributes.style.width = '16px';
            tree.attributes.style.height = '16px';
            tree.attributes.style.opacity = '1.0';
          }

          const symbolElement = renderTree(tree);
          if (symbolElement) {
            setLayerSymbols((prev) => ({
              ...prev,
              [layerId]: symbolElement as JSX.Element,
            }));
          }
        }
      });
    },
    [mapData],
  );

  // effect runs when map initializes AND when new point clouds are added
  useEffect(() => {
    if (!mapContainerRef.current) return;

    // need to nuke in order to re-draw, TODO this can be improved
    if (localMapRef.current) {
      localMapRef.current.remove();
      localMapRef.current = null;
    }
    if (mapRef.current) {
      (mapRef as any).current = null;
    }

    try {
      // Initialize the map with a basic style first
      const mapOptions: MapOptions = {
        container: mapContainerRef.current,
        style: {
          version: 8,
          sources: {},
          layers: [],
        }, // Start with empty style so map loads
        attributionControl: {
          compact: false,
        },
      };

      const newMap = new MLMap(mapOptions);
      localMapRef.current = newMap;
      if (mapRef.current !== undefined) {
        (mapRef as any).current = newMap;
      }

      // Define cursor image loading function
      const loadCursorImage = () => {
        const cursorImage = new Image();
        cursorImage.onload = () => {
          if (newMap.isStyleLoaded()) {
            if (newMap.hasImage('remote-cursor')) {
              newMap.removeImage('remote-cursor');
            }
            newMap.addImage('remote-cursor', cursorImage);
          }
        };
        cursorImage.src =
          'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAyCAYAAAAeP4ixAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAIRSERBVHgB7dnNsdowFAXgQ5INO9OBt9m5BKUDOsAl0AHuIO4AUgF0YKgAOrCpwLDL7kbnPUHAETEY8yy98TejsWf8fnQsc3UBoNfr9WrkZoTwnMxmM8EnCCP0GcLIyXw+P4WJ4CG5tFwuZTQalfAwjFRtt1sJgoCrM4FHxCbPcwnDkGGm8ITcchFmBg/I//gURur4EkbuUZalRFHEMD/hKLkXw4zHY4aZw0HyqMlkwjBbPQI4RJowLQ3DhHCENOVafybPcCmMPMuVMNIGFzpnaUvXnbO0qcvOWdrWVecsr9BFfyav0iTMAM3xf+JZh8PhPIqieDvu93vsdjusVqu75/gNH2iz2SBN0/OEzTjoS6dRmOPeHHf4APIodsH8PT0U3jfB1prHL3gR3nXzaJzp8oo4jnmq8Pfud672xcpRlWUZV4SbnzOtvDXExcYW65Fx4lVKqdN1J1hDmFZjbH4m5qRvrEoGR1xNbrFY2PolPj4lA95YFQUHXIXA7Q42mU6nTq/K24SSJKl7TxFwpVh6q8zurdCCr2guGQwG0EEKff4D7+XU5rf2fTgcRvpxurpwPB6xXq9DffoLHXrkGyvFSlbFVTIV7p6/4QxrKTaPZgqPKFsp5qqYaufUZ111StuqsKrpawk8Yi3FbGngWNtS559SzBUym2MOz6R8gfNjIBOAm2IMD3H3591nAIVez21/ACUSSP4DF2G8AAAAAElFTkSuQmCC';
      };

      newMap.on('load', () => {
        // Add navigation controls
        newMap.addControl(new NavigationControl(), 'top-right');
        newMap.addControl(new ScaleControl(), 'bottom-left');

        const overlaidPCLayers = pointCloudLayers.map((layer) => createPointCloudLayer(layer));

        const deckOverlay = new MapboxOverlay({
          interleaved: true,
          layers: overlaidPCLayers,
        });
        deckOverlayRef.current = deckOverlay;
        newMap.addControl(deckOverlay);

        // Load cursor image initially
        loadCursorImage();
      });

      newMap.on('error', (e) => {
        if (e.error instanceof AJAXError) {
          // Sometimes we can read the error. If its 4xx, show the user the message
          if (e.error.status >= 400 && e.error.status < 500 && e.error.body instanceof Blob) {
            // Read the body of the error
            (async () => {
              const bodyStr = await e.error.body.text();
              try {
                const bodyObj = JSON.parse(bodyStr);

                if ('detail' in bodyObj) {
                  addError(bodyObj.detail, true);
                } else if ('message' in bodyObj && bodyObj['message'] === 'try refresh token') {
                  addError('Session expired, please refresh the page', true);
                } else {
                  addError(bodyStr, true);
                }
              } catch {
                addError(bodyStr, true);
              }
            })();
          } else if (e.error.status == 502 && e.error.message.indexOf('.mvt') !== -1) {
            // This just means database is slow
            addError('PostGIS query took 60+ seconds, database might be overloaded', true);
          } else {
            // Unknown type of error?
            addError('Error loading map data: ' + e.error.message, true);
          }
        } else {
          // Unknown type of error?
          const sourceId = 'sourceId' in e && typeof e.sourceId === 'string' ? e.sourceId : undefined;
          addError('Error loading map data: ' + e.error.message, true, sourceId);
        }
      });

      newMap.on('style.load', () => {
        loadCursorImage();
      });

      // Clean up on unmount
      return () => {
        newMap.remove();
        localMapRef.current = null;
        if (mapRef.current !== undefined) {
          (mapRef as any).current = null;
        }
      };
    } catch (err) {
      console.error('Error initializing map:', err);
      addError('Failed to initialize map: ' + (err instanceof Error ? err.message : String(err)), true);
    }
  }, [addError, pointCloudLayers, createPointCloudLayer, mapRef]); // listen to point cloud layers

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const onClick = (e: any) => {
      const features = map.queryRenderedFeatures(e.point);
      if (!features.length) {
        selectFeature(null);
        return;
      }

      const feature = features[0];
      if (!(typeof feature.source === 'string' && feature.source.startsWith('L') && feature.source.length === 12)) {
        selectFeature(null);
      } else {
        selectFeature(feature);
      }
    };

    map.on('click', onClick);
    return () => {
      map.off('click', onClick);
    };
  }, [mapRef, selectFeature]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (exportPDFControlRef.current) {
      try {
        map.removeControl(exportPDFControlRef.current);
      } catch (err) {
        console.debug('ExportPDFControl removeControl failed (pre-add cleanup)', err);
      }
      exportPDFControlRef.current = null;
    }

    if (!mapId) return;

    const exportPDFControl = new ExportPDFControl(mapId);
    exportPDFControlRef.current = exportPDFControl;
    map.addControl(exportPDFControl, 'top-right');

    return () => {
      if (exportPDFControlRef.current) {
        try {
          map.removeControl(exportPDFControlRef.current);
        } catch (err) {
          console.debug('ExportPDFControl removeControl failed (cleanup)', err);
        }
        exportPDFControlRef.current = null;
      }
    };
  }, [mapRef, mapId]);

  const styleUpdateCounter = useMemo(() => {
    return activeActions.filter((a) => a.updates.style_json).length;
  }, [activeActions]);

  // Use useQuery to fetch the style.json
  const { data: styleData } = useQuery({
    queryKey: ['mapStyle', mapId, styleUpdateCounter],
    queryFn: async () => {
      const url = new URL(`/api/maps/${mapId}/style.json`, window.location.origin);
      const response = await fetch(url.toString());
      if (!response.ok) {
        throw new Error(`Failed to fetch style: ${response.statusText}`);
      }
      return response.json();
    },
    enabled: !!mapId, // Only run query when mapId is available
  });

  // Get current basemap from style metadata or default to first available
  const currentBasemap = useMemo(() => {
    if (styleData?.metadata?.current_basemap) {
      return styleData.metadata.current_basemap;
    }
    return availableBasemaps[0] || '';
  }, [styleData, availableBasemaps]);

  // Separate effect to handle style updates when styleData changes
  useEffect(() => {
    const map = localMapRef.current;
    if (!map || !styleData) return;

    try {
      // Update the style using setStyle
      map.setStyle(styleData);
      loadLegendSymbols(map);

      // If we haven't zoomed yet, zoom to the style's center and zoom level
      // setStyle on purpose does not reset the zoom/center, but it's nice to load a map
      // and be correctly positioned on the data
      if (!hasZoomed) {
        if (styleData.center && styleData.zoom !== undefined) {
          map.jumpTo({
            center: styleData.center,
            zoom: styleData.zoom,
            pitch: styleData.pitch || 0,
            bearing: styleData.bearing || 0,
          });
        }
        setHasZoomed(true);
      }
    } catch (err) {
      console.error('Error updating style:', err);
      addError('Failed to update map style: ' + (err instanceof Error ? err.message : String(err)), true);
    }
  }, [styleData, addError, loadLegendSymbols, hasZoomed]); // Update when styleData changes

  useEffect(() => {
    if (!localMapRef.current) return;

    const map = localMapRef.current;
    if (map && !map.isStyleLoaded()) return;

    const style = map?.getStyle();
    if (!style || !style.layers) return;

    style.layers.forEach((layer) => {
      if ('source' in layer && layer.source) {
        const visibility = hiddenLayerIDs.includes(layer.source as string) ? 'none' : 'visible';
        map.setLayoutProperty(layer.id, 'visibility', visibility);
      }
    });
  }, [hiddenLayerIDs]);

  // Update the points source when pointer positions change
  useEffect(() => {
    const map = localMapRef.current;
    if (map && map.isStyleLoaded()) {
      const source = map.getSource('pointer-positions');
      if (source) {
        (source as maplibregl.GeoJSONSource).setData(pointsGeoJSON);
      }
    }
  }, [pointsGeoJSON]);

  const [inputValue, setInputValue] = useState('');
  const readyStateRef = useRef<number>(readyState);

  useEffect(() => {
    readyStateRef.current = readyState;
  }, [readyState]);

  // Function to send a message
  const sendMessage = async (text: string) => {
    if (!text.trim()) return;

    setInputValue(''); // Clear input after preparing to send

    const userMessage: ChatCompletionUserMessageParam = {
      role: 'user',
      content: text,
    };

    // Create and add ephemeral action
    const actionId = `send-message-${Date.now()}`;
    const sendingAction: EphemeralAction = {
      map_id: mapId,
      ephemeral: true,
      action_id: actionId,
      action: 'Sending message to Kue...',
      timestamp: new Date().toISOString(),
      completed_at: null,
      layer_id: null,
      status: 'active',
      updates: {
        style_json: false,
      },
    };

    try {
      let conversationIdToUse: number | null = conversationId;

      // If no conversation, create one first
      if (conversationIdToUse === null) {
        // Creating conversation also an ephemeral action
        const createConversationAction: EphemeralAction = {
          map_id: mapId,
          ephemeral: true,
          action_id: `create-conversation-${Date.now()}`,
          action: 'Creating new conversation...',
          timestamp: new Date().toISOString(),
          completed_at: null,
          layer_id: null,
          status: 'active',
          updates: {
            style_json: false,
          },
        };
        setActiveActions((prev) => [...prev, createConversationAction]);

        const createResp = await fetch(`/api/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: project.id }),
        });
        if (!createResp.ok) {
          const err = await createResp.json().catch(() => ({ detail: createResp.statusText }));
          throw new Error(err.detail || createResp.statusText);
        }
        const newConv = (await createResp.json()) as Conversation;
        conversationIdToUse = newConv.id;
        setConversationId(conversationIdToUse);

        // Wait briefly for websocket to connect to the new conversation
        const maxWaitMs = 10000;
        const start = Date.now();
        while (Date.now() - start < maxWaitMs && readyStateRef.current !== ReadyState.OPEN) {
          await new Promise((r) => setTimeout(r, 100));
        }
        setActiveActions((prev) => prev.filter((a) => a.action_id !== createConversationAction.action_id));
      }

      setActiveActions((prev) => [...prev, sendingAction]);

      const sendBody: MessageSendRequest = {
        message: userMessage,
        selected_feature: null,
      };
      if (selectedFeature) {
        sendBody.selected_feature = {
          layer_id: selectedFeature.source,
          attributes: selectedFeature.properties,
        };
      }

      const response = await fetch(`/api/maps/conversations/${conversationIdToUse}/maps/${mapId}/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(sendBody),
      });

      if (response.ok) {
        await response.json();
        invalidateProjectData();
      } else {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || response.statusText);
      }
    } catch (error) {
      addError(error instanceof Error ? error.message : 'Network error', true);
    } finally {
      // Remove the ephemeral action when done
      setActiveActions((prev) => prev.filter((a) => a.action_id !== actionId));
    }
  };

  // Handle input submission
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      sendMessage(inputValue);
      setInputValue('');
    }
  };

  // Add basemap control when map and basemaps are available
  useEffect(() => {
    const map = localMapRef.current;
    if (map && availableBasemaps.length > 0 && !basemapControlRef.current) {
      // Use current basemap from style or default to first available
      const initialBasemap = currentBasemap || availableBasemaps[0];
      // Create control with a no-op callback initially to avoid dependency issues
      const basemapControl = new BasemapControl(availableBasemaps, initialBasemap, basemapDisplayNames, () => undefined);
      basemapControlRef.current = basemapControl;
      map.addControl(basemapControl, 'top-right');
      // Immediately update with the real callback
      basemapControl.updateCallback(handleBasemapChange);
    }
  }, [availableBasemaps, currentBasemap, basemapDisplayNames, handleBasemapChange]);

  // Update basemap control when basemap changes
  useEffect(() => {
    if (basemapControlRef.current && currentBasemap) {
      basemapControlRef.current.updateBasemap(currentBasemap);
    }
  }, [currentBasemap]);

  // Update basemap control callback when handleBasemapChange changes
  useEffect(() => {
    if (basemapControlRef.current) {
      basemapControlRef.current.updateCallback(handleBasemapChange);
    }
  }, [handleBasemapChange]);

  // Effect to log when attribute table is opened/closed
  useEffect(() => {
    if (showAttributeTable && selectedLayer) {
      // Debug: Opening attributes for layer
    }
  }, [showAttributeTable, selectedLayer]);

  // Find the last message in the conversation history
  const lastMsg: SanitizedMessage | undefined = mapTree?.tree
    .find((node) => node.map_id === mapId)
    ?.messages.sort((a, b) => {
      if (a.created_at && b.created_at) {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      return 0;
    })[0];

  // Determine the last assistant message to display. Only show if it's the very
  // last message in the conversation and has text content.
  const lastAssistantMsg: string | undefined = lastMsg && lastMsg.role === 'assistant' ? lastMsg.content : undefined;

  // Determine the last user message for the input placeholder.
  const lastUserMsg: string | undefined = lastMsg && lastMsg.role === 'user' ? lastMsg.content : undefined;

  // especially chat disconnected errors happen all the time and shouldn't
  // override the text box
  const criticalErrors = errors.filter((e) => e.shouldOverrideMessages);

  return (
    <>
      <div className={`relative map-container ${className} grow max-h-screen`} style={{ width, height }}>
        <div ref={mapContainerRef} style={{ width: '100%', height: '100%', minHeight: '100vh' }} className="bg-slate-950" />

        {/* Render the attribute table if showAttributeTable is true */}
        {selectedLayer && (
          <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50 w-4/5 max-w-4xl">
            <AttributeTable layer={selectedLayer} isOpen={showAttributeTable} onClose={() => setShowAttributeTable(false)} />
          </div>
        )}

        {mapData && openDropzone && (
          <LayerList
            project={project}
            currentMapData={mapData}
            mapRef={mapRef}
            openDropzone={openDropzone}
            isInConversation={conversationId !== null}
            readyState={readyState}
            activeActions={activeActions}
            setShowAttributeTable={setShowAttributeTable}
            setSelectedLayer={setSelectedLayer}
            updateMapData={invalidateMapData}
            layerSymbols={layerSymbols}
            zoomHistory={zoomHistory}
            zoomHistoryIndex={zoomHistoryIndex}
            setZoomHistoryIndex={setZoomHistoryIndex}
            uploadingFiles={uploadingFiles}
            demoConfig={demoConfig}
            hiddenLayerIDs={hiddenLayerIDs}
            toggleLayerVisibility={toggleLayerVisibility}
            errors={errors}
          />
        )}
        {selectedFeature && (
          <Card className="absolute bottom-10 left-4 max-h-[60vh] overflow-auto py-2 rounded-sm border-0 gap-2 max-w-72 w-full">
            <CardHeader className="px-2">
              <CardTitle className="text-base flex justify-between items-center gap-2">
                <div className="flex gap-2 items-baseline">
                  {mapData?.layers.find((l) => l.id === selectedFeature.source) ? (
                    <>
                      <span>{mapData?.layers.find((l) => l.id === selectedFeature.source)?.name}</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {mapData?.layers.find((l) => l.id === selectedFeature.source)?.type}
                      </span>
                    </>
                  ) : (
                    <span>Selected feature</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      if (selectedFeature && selectedFeature.geometry && mapRef.current) {
                        const map = mapRef.current;
                        const feature_bbox = bbox(selectedFeature.geometry);
                        map.fitBounds(
                          [
                            [feature_bbox[0], feature_bbox[1]],
                            [feature_bbox[2], feature_bbox[3]],
                          ],
                          {
                            padding: 50,
                            duration: 1000,
                          },
                        );
                      }
                    }}
                    className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                    title="Zoom to feature"
                  >
                    <ZoomIn className="h-4 w-4 cursor-pointer" />
                  </button>
                  <button
                    onClick={() => selectFeature(null)}
                    className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                    title="Deselect feature"
                  >
                    <X className="h-4 w-4 cursor-pointer" />
                  </button>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="px-2 max-h-[50vh] overflow-auto">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-1 pr-2 font-medium">Attribute</th>
                      <th className="text-left py-1 font-medium">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedFeature.properties &&
                      Object.entries(selectedFeature.properties).map(([key, value]) => (
                        <tr key={key} className="border-b border-gray-100 dark:border-gray-700" title={`Type: ${typeof value}`}>
                          <td className="py-1 pr-2 font-mono text-gray-600 dark:text-gray-400 break-all">{key}</td>
                          <td className="py-1 font-mono break-all">{String(value)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
        {/* Message display component - always show parent div, animate height */}
        {(criticalErrors.length > 0 || activeActions.length > 0 || lastAssistantMsg) && (
          <div
            className={`z-30 absolute bottom-12 mb-[34px] opacity-90 left-3/5 transform -translate-x-1/2 w-4/5 max-w-lg overflow-auto bg-white dark:bg-gray-800 rounded-t-md shadow-md p-2 text-sm transition-all duration-300 max-h-40 h-auto ${errors.length > 0 ? 'border-red-800' : ''}`}
          >
            {criticalErrors.length > 0 ? (
              <div className="space-y-1 max-h-20">
                {criticalErrors.map((error) => (
                  <div key={error.id} className="flex items-center justify-between">
                    <div className="flex flex-col flex-1 mr-2">
                      <span className="text-red-400">{error.message}</span>
                      <span className="text-xs text-slate-500 dark:text-gray-400">{error.timestamp.toLocaleTimeString()}</span>
                    </div>
                    <button
                      onClick={() => dismissError(error.id)}
                      className="text-white cursor-pointer hover:underline shrink-0"
                      title="Dismiss error"
                    >
                      Dismiss
                    </button>
                  </div>
                ))}
              </div>
            ) : activeActions.length > 0 ? (
              <div className="flex items-center justify-between">
                <ol className="space-y-1">
                  {activeActions.map((action, actionIndex) => (
                    <li key={`${action.action_id}-${actionIndex}`} className="flex items-center">
                      {getActionIcon(action.action)}
                      <span>{action.action}</span>
                    </li>
                  ))}
                </ol>
                {isCancelling ? (
                  <span className="text-white ml-2 shrink-0">Cancelling...</span>
                ) : (
                  <button className="text-white cursor-pointer ml-2 shrink-0 hover:underline" onClick={() => setIsCancelling(true)}>
                    Cancel
                  </button>
                )}
              </div>
            ) : lastAssistantMsg ? (
              <div className={KUE_MESSAGE_STYLE}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{lastAssistantMsg}</ReactMarkdown>
              </div>
            ) : null}
          </div>
        )}
        <div
          className={`z-30 absolute bottom-12 left-3/5 transform -translate-x-1/2 w-4/5 max-w-xl bg-white dark:bg-gray-800 shadow-md focus-within:ring-2 focus-within:ring-white/30 flex items-center border border-input bg-input rounded-md`}
        >
          <Input
            className={`flex-1 border-none shadow-none !bg-transparent focus:!ring-0 focus:!ring-offset-0 focus-visible:!ring-0 focus-visible:!ring-offset-0 focus-visible:!outline-none`}
            placeholder={lastUserMsg || 'Type in for Kue to do something...'}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          {selectedFeature && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span onClick={() => selectFeature(null)} className={`px-2 hover:cursor-pointer text-gray-400 hover:text-gray-200`}>
                  <MousePointerClick className="h-6 w-6 inline-block" />
                </span>
              </TooltipTrigger>
              <TooltipContent>
                <p>Kue can see your selected feature</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      <VersionVisualization
        mapTree={mapTree}
        conversationId={conversationId}
        currentMapId={mapId}
        conversations={conversations}
        conversationsEnabled={conversationsEnabled}
        setConversationId={setConversationId}
        activeActions={activeActions}
      />
    </>
  );
}
