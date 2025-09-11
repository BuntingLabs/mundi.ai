// Copyright Bunting Labs, Inc. 2025

import { ShareEmbedModal } from '@mundi/ee';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  CodeXml,
  Database,
  Info,
  Link,
  Loader2,
  Plus,
  Server,
  Sheet,
  SignalHigh,
  SignalLow,
  Upload,
} from 'lucide-react';
import { Map as MLMap } from 'maplibre-gl';
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ReadyState } from 'react-use-websocket';
import { toast } from 'sonner';
import { AddRemoteDataSource } from '@/components/AddRemoteDataSource';
import { ConnectESRIFeatureService } from '@/components/ConnectESRIFeatureService';
import { ConnectGoogleSheets } from '@/components/ConnectGoogleSheets';
import { ConnectWFS } from '@/components/ConnectWFS';
import EditableTitle from '@/components/EditableTitle';
import { LayerListItem } from '@/components/LayerListItem';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { ErrorEntry } from '../lib/frontend-types';
import type { EphemeralAction, MapData, MapLayer, MapProject, PostgresConnectionDetails } from '../lib/types';

interface UploadingFile {
  id: string;
  file: File;
  progress: number;
  status: 'uploading' | 'completed' | 'error';
  error?: string;
}

interface LayerListProps {
  project: MapProject;
  currentMapData: MapData;
  mapRef: React.RefObject<MLMap | null>;
  openDropzone: () => void;
  activeActions: EphemeralAction[];
  readyState: number;
  isInConversation: boolean;
  setShowAttributeTable: (show: boolean) => void;
  setSelectedLayer: (layer: MapLayer | null) => void;
  updateMapData: () => void;
  layerSymbols: { [layerId: string]: JSX.Element };
  zoomHistory: Array<{ bounds: [number, number, number, number] }>;
  zoomHistoryIndex: number;
  setZoomHistoryIndex: React.Dispatch<React.SetStateAction<number>>;
  uploadingFiles?: UploadingFile[];
  demoConfig: { available: boolean; description: string };
  hiddenLayerIDs: string[];
  toggleLayerVisibility: (layerId: string) => void;
  errors: ErrorEntry[];
}

const LayerList: React.FC<LayerListProps> = ({
  project,
  currentMapData,
  mapRef,
  openDropzone,
  readyState,
  activeActions,
  isInConversation,
  setShowAttributeTable,
  setSelectedLayer,
  updateMapData,
  layerSymbols,
  zoomHistory,
  zoomHistoryIndex,
  setZoomHistoryIndex,
  uploadingFiles,
  demoConfig,
  hiddenLayerIDs,
  toggleLayerVisibility,
  errors,
}) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPostgisDialog, setShowPostgisDialog] = useState(false);

  // Helper function to get errors for a specific source/layer ID
  const getLayerErrors = (layerId: string): ErrorEntry[] => {
    return errors.filter((error) => error.sourceId === layerId);
  };

  // Component to render legend symbol for a layer
  const LayerLegendSymbol = ({ layerDetails }: { layerDetails: MapLayer }) => {
    // Return cached symbol if available, otherwise null
    return layerSymbols[layerDetails.id] || null;
  };
  const [connectionMethod, setConnectionMethod] = useState<'demo' | 'uri' | 'fields'>('uri');
  const [postgisForm, setPostgisForm] = useState({
    uri: '',
    host: '',
    port: '5432',
    database: '',
    username: '',
    password: '',
    schema: 'public',
  });
  const [postgisError, setPostgisError] = useState<string | null>(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showRemoteUrlDialog, setShowRemoteUrlDialog] = useState(false);
  const [showWFSDialog, setShowWFSDialog] = useState(false);
  const [showGoogleSheetsDialog, setShowGoogleSheetsDialog] = useState(false);
  const [showESRIDialog, setShowESRIDialog] = useState(false);
  const [portError, setPortError] = useState<string | null>(null);

  // Fetch PostGIS sources (database connections) for this project
  const { data: projectSources } = useQuery({
    queryKey: ['project', project.id, 'sources'],
    queryFn: async () => {
      const response = await fetch(`/api/projects/${project.id}/sources`);
      if (!response.ok) throw new Error('Failed to fetch project sources');
      return (await response.json()) as PostgresConnectionDetails[];
    },
    retry: 5,
    retryDelay: (attempt) => 1000 * attempt,
  });

  const postgisConnectionMutation = useMutation({
    mutationFn: async (connectionUri: string) => {
      const response = await fetch(`/api/projects/${currentMapData.project_id}/postgis-connections`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ connection_uri: connectionUri }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || response.statusText);
      }

      return response.json();
    },
    onSuccess: () => {
      toast.success('PostgreSQL connection saved successfully! Refreshing...');
      setShowPostgisDialog(false);
      // Reset form
      setPostgisForm({
        uri: '',
        host: '',
        port: '5432',
        database: '',
        username: '',
        password: '',
        schema: 'public',
      });

      // Invalidate the project query to refresh the data
      queryClient.invalidateQueries({ queryKey: ['project', currentMapData.project_id] });
      queryClient.invalidateQueries({ queryKey: ['project', currentMapData.project_id, 'map'] });
      queryClient.invalidateQueries({ queryKey: ['project', currentMapData.project_id, 'sources'] });
    },
    onError: (error: Error) => {
      setPostgisError(error.message);
    },
  });

  const deleteConnectionMutation = useMutation({
    mutationFn: async ({ projectId, connectionId }: { projectId: string; connectionId: string }) => {
      const response = await fetch(`/api/projects/${projectId}/postgis-connections/${connectionId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || response.statusText);
      }

      return response.json();
    },
    onSuccess: () => {
      toast.success('Database connection deleted successfully');
      // Invalidate the project query to refresh the data
      queryClient.invalidateQueries({ queryKey: ['project', project.id] });
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'map'] });
      queryClient.invalidateQueries({ queryKey: ['project', project.id, 'sources'] });
    },
    onError: (error: Error) => {
      toast.error(`Failed to delete connection: ${error.message}`);
    },
  });

  const renameMutation = useMutation({
    mutationFn: async ({ layerId, newName }: { layerId: string; newName: string }) => {
      const response = await fetch(`/api/layer/${layerId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: newName }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || response.statusText);
      }

      return response.json();
    },
    onSuccess: () => {
      updateMapData();
      toast.success('Layer renamed');
    },
    onError: (error) => {
      console.error('Error renaming layer:', error);
      toast.error(`Error renaming layer: ${error.message}`);
    },
  });

  const handlePostgisConnect = async () => {
    if (!currentMapData?.project_id) {
      toast.error('No project ID available');
      return;
    }

    // Simple inline validation for numeric port when using field-based connection method
    if (connectionMethod === 'fields') {
      if (postgisForm.port && !/^\d+$/.test(postgisForm.port)) {
        setPortError('Port must be a number');
        return;
      }
    }

    let connectionUri = '';
    if (connectionMethod === 'demo') {
      connectionUri = 'DEMO'; // Special marker for backend to use DEMO_POSTGIS_URI
    } else if (connectionMethod === 'uri') {
      connectionUri = postgisForm.uri;
    } else {
      // Build URI from form fields
      connectionUri = `postgresql://${postgisForm.username}:${postgisForm.password}@${postgisForm.host}:${postgisForm.port}/${postgisForm.database}`;
    }

    if (!connectionUri.trim() || (connectionMethod !== 'demo' && connectionUri === '')) {
      setPostgisError('Please provide connection details');
      return;
    }

    setPostgisError(null);
    postgisConnectionMutation.mutate(connectionUri);
  };

  return (
    <Card className="absolute top-4 left-4 max-h-[60vh] overflow-auto py-2 rounded-sm border-0 gap-2 max-w-72 w-full">
      <CardHeader className="px-2">
        <CardTitle className="text-base flex justify-between items-center gap-2">
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger>
                {!isInConversation || readyState === ReadyState.OPEN ? (
                  <span className="text-green-300 inline-block">
                    <SignalHigh />
                  </span>
                ) : (
                  <span className="text-red-300 inline-block">
                    <SignalLow />
                  </span>
                )}
              </TooltipTrigger>
              <TooltipContent>
                <div className="text-sm flex space-x-2">
                  {isInConversation && (
                    <div className={readyState === ReadyState.OPEN ? 'text-green-300' : 'text-red-300'}>
                      chat:{' '}
                      {readyState === ReadyState.OPEN ? (
                        <SignalHigh className="inline-block h-4 w-4" />
                      ) : (
                        <SignalLow className="inline-block h-4 w-4" />
                      )}
                    </div>
                  )}
                </div>
              </TooltipContent>
            </Tooltip>
            <EditableTitle projectId={currentMapData.project_id} title={project?.title} placeholder="Enter map title here" />
          </div>
          <React.Suspense fallback={null}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowShareModal(true)}
                  className="p-0.5 hover:cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600"
                >
                  <CodeXml className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Embed into website</p>
              </TooltipContent>
            </Tooltip>

            <ShareEmbedModal isOpen={showShareModal} onClose={() => setShowShareModal(false)} projectId={currentMapData?.project_id} />
          </React.Suspense>
        </CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        {(currentMapData.layers?.length ?? 0) > 0 ? (
          <ul className="text-sm">
            {(currentMapData.layers ?? []).map((layerDetails: MapLayer) => {
              // Check if this layer has an active action
              const hasActiveAction = activeActions.some((action) => action.layer_id === layerDetails.id);
              const num_highlighted = 0;

              const sridDisplay = layerDetails.metadata?.original_srid ? `EPSG:${layerDetails.metadata.original_srid}` : 'N/A';

              const normalText =
                layerDetails.type === 'raster'
                  ? sridDisplay
                  : num_highlighted > 0
                    ? `${num_highlighted} / ${layerDetails.feature_count ?? 'N/A'}`
                    : String(layerDetails.feature_count ?? 'N/A');

              const hoverText = layerDetails.type === 'raster' ? undefined : sridDisplay;

              // Check for errors associated with this layer
              const layerErrors = getLayerErrors(layerDetails.id);
              const hasErrors = layerErrors.length > 0;

              const getNameClassName = () => {
                if (hiddenLayerIDs.includes(layerDetails.id)) {
                  return 'line-through text-gray-400';
                }
                if (hasErrors) {
                  return 'text-red-300';
                }
                return '';
              };

              // Create title text from error messages if any
              const errorTitle = hasErrors ? layerErrors.map((error) => error.message).join(' | ') : undefined;

              return (
                <li key={layerDetails.id}>
                  <LayerListItem
                    name={layerDetails.name}
                    nameClassName={getNameClassName()}
                    isActive={hasActiveAction}
                    hoverText={hoverText}
                    normalText={normalText}
                    legendSymbol={<LayerLegendSymbol layerDetails={layerDetails} />}
                    layerId={layerDetails.id}
                    isVisible={!hiddenLayerIDs.includes(layerDetails.id)}
                    title={errorTitle}
                    onToggleVisibility={(layerId) => {
                      toggleLayerVisibility(layerId);
                    }}
                    onRename={(layerId, newName) => {
                      renameMutation.mutate({ layerId, newName });
                    }}
                    dropdownActions={{
                      'zoom-to-layer': {
                        label: 'Zoom to layer',
                        disabled: false,
                        action: (layerId) => {
                          const layer = currentMapData.layers?.find((l) => l.id === layerId);
                          if (!layer) {
                            toast.error('Layer not found');
                            return;
                          }
                          if (layer.bounds && layer.bounds.length === 4 && mapRef.current) {
                            mapRef.current.fitBounds(
                              [
                                [layer.bounds[0], layer.bounds[1]],
                                [layer.bounds[2], layer.bounds[3]],
                              ],
                              { padding: 50, animate: true },
                            );
                            toast.success('Zoomed to layer');
                          } else {
                            toast.info('Layer bounds not available for zoom.');
                          }
                        },
                      },
                      'view-attributes': {
                        label: 'View attributes',
                        disabled: false,
                        action: (layerId) => {
                          const layer = currentMapData.layers?.find((l) => l.id === layerId);
                          if (!layer) {
                            toast.error('Layer not found');
                            return;
                          }
                          setSelectedLayer(layer);
                          setShowAttributeTable(true);
                        },
                      },
                      'export-geopackage': {
                        label: 'Export as GeoPackage',
                        disabled: layerDetails.type !== 'vector',
                        action: () => {
                          // TODO: Implement geopackage export
                        },
                      },
                      'delete-layer': {
                        label: 'Delete layer',
                        action: (layerId) => {
                          fetch(`/api/maps/${currentMapData.map_id}/layer/${layerId}`, {
                            method: 'DELETE',
                            headers: { 'Content-Type': 'application/json' },
                          })
                            .then((response) => {
                              if (response.ok) {
                                return response.json();
                              } else {
                                throw new Error(`Failed to delete layer: ${response.statusText}`);
                              }
                            })
                            .then((data) => {
                              toast.success(`Layer successfully removed! Navigating to new map...`);
                              // Navigate to the new child map if dag_child_map_id is present
                              if (data.dag_child_map_id) {
                                setTimeout(() => {
                                  navigate(`/project/${project.id}/${data.dag_child_map_id}`);
                                }, 1000);
                              } else {
                                // Fallback: reload the page
                                window.location.reload();
                              }
                            })
                            .catch((err) => {
                              console.error('Error deleting layer:', err);
                              toast.error(`Error deleting layer: ${err.message}`);
                            });
                        },
                      },
                    }}
                  />
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-slate-500 px-2">No layers to display.</p>
        )}

        {/* Upload Progress section */}
        {uploadingFiles && uploadingFiles.length > 0 && (
          <>
            <div className="flex items-center px-2 py-2">
              <div className="flex-1 h-px bg-gray-300 dark:bg-gray-600"></div>
              <span className="px-3 text-xs font-medium text-gray-600 dark:text-gray-400">UPLOADING</span>
              <div className="flex-1 h-px bg-gray-300 dark:bg-gray-600"></div>
            </div>
            <ul className="space-y-2 text-sm px-2">
              {uploadingFiles.map((uploadingFile) => (
                <li key={uploadingFile.id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-2">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{uploadingFile.file.name}</span>
                    <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                      {uploadingFile.status === 'uploading' && `${uploadingFile.progress}%`}
                      {uploadingFile.status === 'completed' && '✓'}
                      {uploadingFile.status === 'error' && '✗'}
                    </span>
                  </div>

                  {uploadingFile.status === 'uploading' && (
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                      <div
                        className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${uploadingFile.progress}%` }}
                      />
                    </div>
                  )}

                  {uploadingFile.status === 'completed' && (
                    <div className="text-xs text-green-600 dark:text-green-400">Upload completed</div>
                  )}

                  {uploadingFile.status === 'error' && (
                    <div className="text-xs text-red-600 dark:text-red-400">{uploadingFile.error || 'Upload failed'}</div>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}

        {/* Database Sources section */}
        {projectSources && projectSources.length > 0 && (
          <>
            <div className="flex items-center px-2 py-2">
              <div className="flex-1 h-px bg-gray-300 dark:bg-gray-600"></div>
              <span className="px-3 text-xs font-medium text-gray-600 dark:text-gray-400">DATABASES</span>
              <div className="flex-1 h-px bg-gray-300 dark:bg-gray-600"></div>
            </div>
            <ul className="text-sm">
              {projectSources.map((connection, index) =>
                connection.last_error_text ? (
                  <TooltipProvider key={index}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <li
                          className={`flex items-center justify-between px-2 py-1 gap-2 hover:bg-slate-100 dark:hover:bg-gray-600 cursor-pointer group`}
                          onClick={() => {
                            deleteConnectionMutation.mutate({ projectId: project.id, connectionId: connection.connection_id });
                          }}
                        >
                          <span className="font-medium truncate flex items-center gap-2 text-red-400">
                            <span className="text-red-400">⚠</span>
                            Connection Error
                          </span>
                          <div className="flex-shrink-0">
                            <div className="group-hover:hidden">
                              <span className="text-xs text-red-400">Error</span>
                            </div>
                            <div className="hidden group-hover:block w-4 h-4">
                              <svg className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                                />
                              </svg>
                            </div>
                          </div>
                        </li>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>{connection.last_error_text}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : !connection.is_documented ? (
                  <li key={index} className="border border-gray-200 dark:border-gray-700 rounded-lg p-2 mx-2 mb-2">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate flex items-center gap-2">
                        <Database className="h-4 w-4" />
                        {connection.friendly_name || 'Loading...'}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                        {connection.processed_tables_count}/{connection.table_count}
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                      <div
                        className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${((connection.processed_tables_count ?? 0) / connection.table_count) * 100}%` }}
                      />
                    </div>
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">Documenting database...</div>
                  </li>
                ) : (
                  <li
                    key={index}
                    className={`flex items-center justify-between px-2 py-1 gap-2 hover:bg-slate-100 dark:hover:bg-gray-600 cursor-pointer group ${connection.friendly_name === 'Loading...' ? 'animate-pulse' : ''}`}
                    onClick={() => navigate(`/postgis/${connection.connection_id}`)}
                  >
                    <span className="font-medium truncate flex items-center gap-2" title={connection.friendly_name || undefined}>
                      <Database className="h-4 w-4" />
                      {connection.friendly_name}
                    </span>
                    <div className="flex-shrink-0">
                      <div className="group-hover:hidden">
                        <span className="text-xs text-slate-500 dark:text-gray-400">{connection.table_count} tables</span>
                      </div>
                      <div className="hidden group-hover:block w-4 h-4">
                        <Info className="w-4 h-4" />
                      </div>
                    </div>
                  </li>
                ),
              )}
            </ul>
          </>
        )}
      </CardContent>
      <CardFooter className="flex justify-between items-center px-2">
        <div className="flex items-center gap-1">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  className="p-0.5 hover:cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600"
                  disabled={zoomHistoryIndex <= 0}
                  onClick={() => {
                    if (zoomHistoryIndex > 0 && mapRef.current) {
                      const newIndex = zoomHistoryIndex - 1;
                      const historyItem = zoomHistory[newIndex];
                      if (historyItem?.bounds && historyItem.bounds.length === 4) {
                        const targetBounds = historyItem.bounds;
                        mapRef.current.fitBounds(
                          [
                            [targetBounds[0], targetBounds[1]],
                            [targetBounds[2], targetBounds[3]],
                          ],
                          { animate: true },
                        );
                        setZoomHistoryIndex(newIndex);
                      } else {
                        console.error('Previous zoom - invalid historyItem or bounds:', historyItem);
                      }
                    }
                  }}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Previous location</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <span className="text-xs text-slate-500 dark:text-gray-400">Zoom</span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  className="p-0.5 hover:cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600"
                  disabled={zoomHistoryIndex >= zoomHistory.length - 1}
                  onClick={() => {
                    if (zoomHistoryIndex < zoomHistory.length - 1 && mapRef.current) {
                      const newIndex = zoomHistoryIndex + 1;
                      const historyItem = zoomHistory[newIndex];
                      if (historyItem?.bounds && historyItem.bounds.length === 4) {
                        const targetBounds = historyItem.bounds;
                        mapRef.current.fitBounds(
                          [
                            [targetBounds[0], targetBounds[1]],
                            [targetBounds[2], targetBounds[3]],
                          ],
                          { animate: true },
                        );
                        setZoomHistoryIndex(newIndex);
                      } else {
                        console.error('Next zoom - invalid historyItem or bounds:', historyItem);
                      }
                    }
                  }}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Next location</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <div className="flex items-center gap-1">
          <TooltipProvider>
            <DropdownMenu>
              <Tooltip>
                <TooltipTrigger asChild>
                  <DropdownMenuTrigger asChild>
                    <Button size="sm" variant="ghost" className="p-0.5 hover:cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600">
                      <Plus className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Add layer source</p>
                </TooltipContent>
              </Tooltip>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={openDropzone} className="cursor-pointer">
                  <Upload className="h-4 w-4 mr-2" />
                  Upload file
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setShowRemoteUrlDialog(true)} className="cursor-pointer">
                  <Link className="h-4 w-4 mr-2" />
                  Add remote URL
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setShowWFSDialog(true)} className="cursor-pointer">
                  <Server className="h-4 w-4 mr-2" />
                  Connect to WFS
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setShowGoogleSheetsDialog(true)} className="cursor-pointer">
                  <Sheet className="h-4 w-4 mr-2" />
                  Google Sheets
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setShowESRIDialog(true)} className="cursor-pointer">
                  <Database className="h-4 w-4 mr-2" />
                  ESRI Feature Service
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </TooltipProvider>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  className="p-0.5 hover:cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-600"
                  onClick={() => setShowPostgisDialog(true)}
                >
                  <Database className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Load PostGIS</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* PostGIS Connection Dialog */}
        <Dialog
          open={showPostgisDialog}
          onOpenChange={(open) => {
            setShowPostgisDialog(open);
            if (!open) {
              setPostgisError(null);
            }
          }}
        >
          <DialogContent className="sm:max-w-[500px]">
            <DialogHeader>
              <DialogTitle>Add a PostGIS Database</DialogTitle>
              <DialogDescription>
                Your database connection details will be stored on the server. Read-only access is best.{' '}
                <a
                  href="https://docs.mundi.ai/guides/connecting-to-postgis/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-300 hover:text-blue-400 underline"
                >
                  Read our tutorial on PostGIS here.
                </a>
              </DialogDescription>
            </DialogHeader>

            <div className="grid gap-4 py-4">
              {/* Connection Method Toggle */}
              <div className="flex space-x-2">
                {demoConfig.available && (
                  <Button
                    type="button"
                    variant={connectionMethod === 'demo' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setConnectionMethod('demo')}
                    className="flex-1 hover:cursor-pointer"
                  >
                    Demo Database
                  </Button>
                )}
                <Button
                  type="button"
                  variant={connectionMethod === 'uri' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setConnectionMethod('uri')}
                  className="flex-1 hover:cursor-pointer"
                >
                  Database URI
                </Button>
                <Button
                  type="button"
                  variant={connectionMethod === 'fields' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setConnectionMethod('fields')}
                  className="flex-1 hover:cursor-pointer"
                >
                  Connection Details
                </Button>
              </div>

              {connectionMethod === 'demo' ? (
                <div className="space-y-2">
                  <p className="text-sm text-gray-300">
                    {demoConfig.description} We provide it as a demo to preview Mundi's capabilities, especially for users with sensitive
                    PostGIS databases who would rather self-host or use an on-premise deployment.
                  </p>
                </div>
              ) : connectionMethod === 'uri' ? (
                <div className="space-y-2">
                  <label htmlFor="uri" className="text-sm font-medium">
                    Database URI
                  </label>
                  <Input
                    id="uri"
                    placeholder="postgresql://username:password@host:port/database"
                    value={postgisForm.uri}
                    onChange={(e) => {
                      setPostgisForm((prev) => ({
                        ...prev,
                        uri: e.target.value,
                      }));
                      setPostgisError(null);
                    }}
                  />
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label htmlFor="host" className="text-sm font-medium">
                        Host
                      </label>
                      <Input
                        id="host"
                        placeholder="localhost"
                        value={postgisForm.host}
                        onChange={(e) => {
                          setPostgisForm((prev) => ({
                            ...prev,
                            host: e.target.value,
                          }));
                          setPostgisError(null);
                        }}
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="port" className="text-sm font-medium">
                        Port
                      </label>
                      <Input
                        id="port"
                        placeholder="5432"
                        value={postgisForm.port}
                        aria-invalid={!!portError}
                        onChange={(e) => {
                          setPostgisForm((prev) => ({
                            ...prev,
                            port: e.target.value,
                          }));
                          // Inline numeric validation
                          const value = e.target.value;
                          if (value && !/^\d+$/.test(value)) {
                            setPortError('Port must be a number');
                          } else {
                            setPortError(null);
                          }
                          setPostgisError(null);
                        }}
                      />
                      {portError && <p className="text-destructive text-xs">{portError}</p>}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label htmlFor="database" className="text-sm font-medium">
                        Database
                      </label>
                      <Input
                        id="database"
                        placeholder="postgres"
                        value={postgisForm.database}
                        onChange={(e) => {
                          setPostgisForm((prev) => ({
                            ...prev,
                            database: e.target.value,
                          }));
                          setPostgisError(null);
                        }}
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="schema" className="text-sm font-medium">
                        Schema
                      </label>
                      <Input
                        id="schema"
                        placeholder="public"
                        value={postgisForm.schema}
                        onChange={(e) => {
                          setPostgisForm((prev) => ({
                            ...prev,
                            schema: e.target.value,
                          }));
                          setPostgisError(null);
                        }}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label htmlFor="username" className="text-sm font-medium">
                        Username
                      </label>
                      <Input
                        id="username"
                        placeholder="postgres"
                        value={postgisForm.username}
                        onChange={(e) => {
                          setPostgisForm((prev) => ({
                            ...prev,
                            username: e.target.value,
                          }));
                          setPostgisError(null);
                        }}
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="password" className="text-sm font-medium">
                        Password
                      </label>
                      <Input
                        id="password"
                        type="password"
                        placeholder="password"
                        value={postgisForm.password}
                        onChange={(e) => {
                          setPostgisForm((prev) => ({
                            ...prev,
                            password: e.target.value,
                          }));
                          setPostgisError(null);
                        }}
                      />
                    </div>
                  </div>
                </>
              )}

              {/* Error Callout */}
              {postgisError && (
                <div className="flex items-start gap-3 p-3 bg-red-50 border border-red-200 rounded-md">
                  <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
                  <div className="text-sm text-red-700">
                    {postgisError}{' '}
                    <a
                      href="https://docs.mundi.ai/guides/connecting-to-postgis/#debugging-common-problems"
                      target="_blank"
                      className="text-blue-500 hover:text-blue-600 underline"
                      rel="noopener"
                    >
                      Refer to our documentation on PostGIS errors.
                    </a>
                  </div>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowPostgisDialog(false)} className="hover:cursor-pointer">
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handlePostgisConnect}
                className="hover:cursor-pointer"
                disabled={postgisConnectionMutation.isPending}
              >
                {postgisConnectionMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Adding Connection...
                  </>
                ) : (
                  'Add Connection'
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <AddRemoteDataSource
          isOpen={showRemoteUrlDialog}
          onClose={() => setShowRemoteUrlDialog(false)}
          mapId={currentMapData?.map_id}
          onSuccess={updateMapData}
        />

        <ConnectWFS
          isOpen={showWFSDialog}
          onClose={() => setShowWFSDialog(false)}
          mapId={currentMapData?.map_id}
          onSuccess={updateMapData}
        />

        <ConnectGoogleSheets
          isOpen={showGoogleSheetsDialog}
          onClose={() => setShowGoogleSheetsDialog(false)}
          mapId={currentMapData?.map_id}
          onSuccess={updateMapData}
        />
        <ConnectESRIFeatureService
          isOpen={showESRIDialog}
          onClose={() => setShowESRIDialog(false)}
          mapId={currentMapData?.map_id}
          onSuccess={updateMapData}
        />
      </CardFooter>
    </Card>
  );
};

export default LayerList;
