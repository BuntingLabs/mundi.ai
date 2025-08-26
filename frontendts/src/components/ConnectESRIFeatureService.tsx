// Copyright (C) 2025 Bunting Labs, Inc.

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.

// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

import { AlertTriangle, Loader2 } from 'lucide-react';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

// Validate ESRI Feature Service URL client-side
const validateEsriFeatureServiceUrl = (url: string): { isValid: boolean; error?: string } => {
  if (!url.trim()) {
    return { isValid: false, error: 'URL is required' };
  }

  try {
    const parsedUrl = new URL(url);

    // Check if it's HTTP/HTTPS
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      return { isValid: false, error: 'URL must use HTTP or HTTPS protocol' };
    }

    // Check if it's an ESRI Feature Service or Map Service URL
    const path = parsedUrl.pathname.toLowerCase();
    if (!path.includes('/featureserver') && !path.includes('/mapserver')) {
      return { isValid: false, error: 'URL must contain /FeatureServer or /MapServer' };
    }

    // Check if URL ends with service endpoint (optional layer ID is OK)
    if (!path.match(/\/(featureserver|mapserver)(?:\/\d+)?(?:\/query)?$/i)) {
      return { isValid: false, error: 'URL must end with /FeatureServer, /MapServer, or include a layer ID (e.g., /FeatureServer/0)' };
    }

    return { isValid: true };
  } catch (_error) {
    return { isValid: false, error: 'Invalid URL format' };
  }
};

// Transform ESRI Feature Service URL to appropriate query format for GDAL ESRIJSON driver
const transformEsriFeatureServiceUrl = (url: string): string => {
  try {
    const parsedUrl = new URL(url);
    let transformedUrl = url;

    // If the URL doesn't already have /query, append it for layer-specific URLs
    if (parsedUrl.pathname.match(/\/(featureserver|mapserver)\/\d+$/i)) {
      transformedUrl += '/query';
    } else if (parsedUrl.pathname.match(/\/(featureserver|mapserver)$/i)) {
      // For base service URLs, append /0/query to get the first layer
      transformedUrl += '/0/query';
    }

    // Parse existing query parameters
    const urlObject = new URL(transformedUrl);
    const params = urlObject.searchParams;

    // Set required parameters if not already present
    if (!params.has('f')) {
      params.set('f', 'pjson');
    }

    // Add resultRecordCount limit to prevent timeouts on large datasets (this is critical)
    if (!params.has('resultRecordCount') && !params.has('maxRecordCount')) {
      params.set('resultRecordCount', '1000');
    }

    return urlObject.toString();
  } catch (_error) {
    return url;
  }
};

interface ConnectESRIFeatureServiceProps {
  isOpen: boolean;
  onClose: () => void;
  mapId?: string;
  onSuccess?: () => void;
}

export const ConnectESRIFeatureService: React.FC<ConnectESRIFeatureServiceProps> = ({ isOpen, onClose, mapId, onSuccess }) => {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [layerName, setLayerName] = useState('');
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [esriValidation, setEsriValidation] = useState<{ isValid: boolean; error?: string } | null>(null);

  const handleConnect = async () => {
    if (!mapId) {
      toast.error('No map ID available');
      return;
    }

    if (!layerName.trim()) {
      setError('Please provide a layer name');
      return;
    }

    if (!url.trim()) {
      setError('Please provide an ESRI Feature Service URL');
      return;
    }

    // Validate ESRI Feature Service URL
    const validation = validateEsriFeatureServiceUrl(url);
    if (!validation.isValid) {
      setError(validation.error || 'Invalid ESRI Feature Service URL');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Transform ESRI Feature Service URL to proper query format
      const processedUrl = transformEsriFeatureServiceUrl(url);

      const response = await fetch(`/api/maps/${mapId}/layers/remote`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: processedUrl,
          name: layerName,
          add_layer_to_map: true,
          source_type: 'vector', // ESRI Feature Service is treated as vector on backend
        }),
      });

      if (response.ok) {
        const data = await response.json();
        toast.success('ESRI Feature Service layer added successfully!');
        handleClose();
        onSuccess?.();

        // Navigate to the new child map if dag_child_map_id is present
        if (data.dag_child_map_id && projectId) {
          setTimeout(() => {
            navigate(`/project/${projectId}/${data.dag_child_map_id}`);
          }, 1000);
        }
      } else {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        setError(errorData.detail || response.statusText);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Network error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setLayerName('');
    setUrl('');
    setError(null);
    setEsriValidation(null);
    onClose();
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) {
          handleClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Connect to ESRI Feature Service</DialogTitle>
          <DialogDescription>
            Connect to a public ESRI ArcGIS Feature Service or Map Service to load vector data from a remote server.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="space-y-2">
            <label htmlFor="layer-name" className="text-sm font-medium">
              Layer Name
            </label>
            <Input
              id="layer-name"
              placeholder="Enter a name for this layer"
              value={layerName}
              onChange={(e) => {
                setLayerName(e.target.value);
                setError(null);
              }}
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="esri-url" className="text-sm font-medium">
              ESRI Service URL
            </label>
            <Input
              id="esri-url"
              placeholder="https://services.arcgis.com/example/FeatureServer/0"
              value={url}
              onChange={(e) => {
                const newUrl = e.target.value;
                setUrl(newUrl);
                setError(null);

                // Real-time validation for ESRI Feature Service URL
                if (newUrl.trim()) {
                  const validation = validateEsriFeatureServiceUrl(newUrl);
                  setEsriValidation(validation);
                } else {
                  setEsriValidation(null);
                }
              }}
            />
            <div className="text-xs text-gray-600 dark:text-gray-400">
              <p>Enter a Feature Service or Map Service URL:</p>
              <ul className="list-disc ml-4 mt-1 space-y-1">
                <li>https://example.com/arcgis/rest/services/MyService/FeatureServer</li>
                <li>https://example.com/arcgis/rest/services/MyService/FeatureServer/0</li>
                <li>https://example.com/arcgis/rest/services/MyService/MapServer/1</li>
              </ul>
            </div>
            {esriValidation && !esriValidation.isValid && (
              <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded-md">
                <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-red-700">{esriValidation.error}</div>
              </div>
            )}
            {esriValidation && esriValidation.isValid && <div className="text-xs text-green-600">✓ Valid ESRI service URL format</div>}
          </div>

          {/* Error Callout */}
          {error && (
            <div className="flex items-start gap-3 p-3 bg-red-50 border border-red-200 rounded-md">
              <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-red-700">{error}</div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleClose} className="hover:cursor-pointer">
            Cancel
          </Button>
          <Button type="button" onClick={handleConnect} className="hover:cursor-pointer" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Connecting to ESRI Service...
              </>
            ) : (
              'Connect to ESRI Service'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
