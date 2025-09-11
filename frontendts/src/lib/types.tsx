// Copyright Bunting Labs, Inc. 2025

import { ChatCompletionUserMessageParam } from 'openai/resources/chat/completions.mjs';

export interface MapProject {
  id: string;
  title?: string;
  maps: string[];
  created_on: string;
  most_recent_version?: {
    title?: string;
    description?: string;
    last_edited?: string;
  };
  soft_deleted_at?: string;
}

export type ProjectState = { type: 'not_logged_in' } | { type: 'loading' } | { type: 'loaded'; projects: MapProject[] };

// Keep this in sync with backend LayerMetadata (mundi-public/src/routes/postgres_routes.py)
export interface MapLayerMetadata {
  original_filename?: string;
  original_format?: string;
  converted_to?: string;
  original_srid?: number;
  feature_count?: number;
  geometry_type?: string;
  raster_value_stats_b1?: {
    min: number;
    max: number;
  };
  pointcloud_anchor?: {
    lon: number;
    lat: number;
  };
  pointcloud_z_range?: [number, number];
}

export interface MapLayer {
  id: string;
  name: string;
  path: string;
  type: string;
  metadata?: MapLayerMetadata;
  bounds?: number[];
  geometry_type?: string;
  feature_count?: number;
  original_srid?: number;
}

export interface PostgresConnectionDetails {
  connection_id: string;
  table_count: number;
  processed_tables_count: number | null;
  friendly_name: string | null;
  is_documented: boolean;
  last_error_text?: string;
  last_error_timestamp?: string;
}

export interface MapData {
  map_id: string;
  project_id: string;
  layers: MapLayer[];
  changelog: Array<{
    message: string;
    map_state: string;
    last_edited: string;
  }>;
}

// Note: Per-layer diffs for the map detail route have been removed.

export interface PointerPosition {
  lng: number;
  lat: number;
}

export interface PresenceData {
  value: PointerPosition;
  lastSeen: number;
}

export interface EphemeralUpdates {
  style_json: boolean;
}

export interface EphemeralAction {
  map_id: string;
  ephemeral: boolean;
  action_id: string;
  layer_id: string | null;
  action: string;
  timestamp: string;
  completed_at: string | null;
  status: 'active' | 'completed' | 'zoom_action' | 'error';
  updates: EphemeralUpdates;
  bounds?: [number, number, number, number];
  description?: string;
  error_message?: string;
}

/* tree */

export interface SelectedFeature {
  layer_id: string;
  attributes: Record<string, string>;
}

export interface MessageSendRequest {
  message: ChatCompletionUserMessageParam;
  selected_feature: SelectedFeature | null;
}

export interface MessageSendResponse {
  conversation_id: number;
  sent_message: SanitizedMessage;
  message_id: string;
  status: string;
}

export interface CodeBlock {
  language: string;
  code: string;
}

export interface SanitizedToolCall {
  id: string;
  tagline: string;
  icon: 'text-search' | 'brush' | 'wrench' | 'map-plus' | 'cloud-download' | 'zoom-in' | 'qgis';
  code: CodeBlock | null;
  table?: Record<string, string>;
}

export interface SanitizedToolResponse {
  id: string;
  status: 'success' | 'error';
}

export interface SanitizedMessage {
  role: string;
  content?: string;
  has_tool_calls: boolean;
  tool_calls?: SanitizedToolCall[];
  map_id?: string; // Associates the message with a specific map version
  conversation_id?: number; // Associates the message with a specific conversation
  created_at?: string; // Timestamp from backend for proper ordering of messages
  tool_response?: SanitizedToolResponse;
}

export interface MessagesListResponse {
  map_id: string;
  messages: SanitizedMessage[];
}

export interface LayerInfo {
  layer_id: string;
  name: string;
  type: string;
  geometry_type: string | null;
  feature_count: number | null;
}

export interface LayerDiff {
  added_layers: LayerInfo[];
  removed_layers: LayerInfo[];
}

export interface MapNode {
  map_id: string;
  messages: SanitizedMessage[];
  fork_reason: string | null;
  created_on: string;
  diff_from_previous: LayerDiff | null;
}

export interface MapTreeResponse {
  project_id: string;
  tree: MapNode[];
}

export interface Conversation {
  id: number;
  project_id: string;
  owner_uuid: string;
  title?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  first_message_map_id?: string;
}
