// Copyright Bunting Labs, Inc. 2025

import { AlertTriangle, Loader2 } from 'lucide-react';
import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

// Validate WFS URL client-side
const validateWfsUrl = (url: string): { isValid: boolean; error?: string } => {
  if (!url.trim()) {
    return { isValid: false, error: 'URL is required' };
  }

  try {
    const parsedUrl = new URL(url);

    // Check if it's HTTP/HTTPS
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      return { isValid: false, error: 'URL must use HTTP or HTTPS protocol' };
    }

    const params = new URLSearchParams(parsedUrl.search);

    // Check required WFS parameters
    const service = params.get('service')?.toUpperCase();
    const request = params.get('request')?.toUpperCase();
    const version = params.get('version');
    const typename = params.get('typename') || params.get('typeName');

    if (service !== 'WFS') {
      return { isValid: false, error: 'URL must have service=WFS parameter' };
    }

    if (request !== 'GETFEATURE') {
      return { isValid: false, error: 'URL must have request=GetFeature parameter' };
    }

    if (!version) {
      return { isValid: false, error: 'URL must specify a version parameter (e.g., 1.1.0, 2.0.0)' };
    }

    if (!typename) {
      return { isValid: false, error: 'URL must specify a typename parameter' };
    }

    return { isValid: true };
  } catch (_error) {
    return { isValid: false, error: 'Invalid URL format' };
  }
};

interface ConnectWFSProps {
  isOpen: boolean;
  onClose: () => void;
  mapId?: string;
  onSuccess?: () => void;
}

export const ConnectWFS: React.FC<ConnectWFSProps> = ({ isOpen, onClose, mapId, onSuccess }) => {
  const [layerName, setLayerName] = useState('');
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wfsValidation, setWfsValidation] = useState<{ isValid: boolean; error?: string } | null>(null);

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
      setError('Please provide a WFS URL');
      return;
    }

    // Validate WFS URL
    const validation = validateWfsUrl(url);
    if (!validation.isValid) {
      setError(validation.error || 'Invalid WFS URL');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/maps/${mapId}/layers/remote`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: url,
          name: layerName,
          add_layer_to_map: true,
          source_type: 'vector', // WFS is treated as vector on backend
        }),
      });

      if (response.ok) {
        toast.success('WFS layer added successfully!');
        handleClose();
        onSuccess?.();
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
    setWfsValidation(null);
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
          <DialogTitle>Connect to WFS</DialogTitle>
          <DialogDescription>Connect to a Web Feature Service (WFS) endpoint to load vector data from a remote server.</DialogDescription>
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
            <label htmlFor="wfs-url" className="text-sm font-medium">
              WFS Service URL
            </label>
            <Input
              id="wfs-url"
              placeholder="https://example.com/geoserver/wfs?service=WFS&version=1.1.0&request=GetFeature&typename=layer:features&outputFormat=application/json"
              value={url}
              onChange={(e) => {
                const newUrl = e.target.value;
                setUrl(newUrl);
                setError(null);

                // Real-time validation for WFS URL
                if (newUrl.trim()) {
                  const validation = validateWfsUrl(newUrl);
                  setWfsValidation(validation);
                } else {
                  setWfsValidation(null);
                }
              }}
            />
            <div className="text-xs text-gray-600 dark:text-gray-400">
              <p>Paste a WFS GetFeature URL with required parameters:</p>
              <ul className="list-disc ml-4 mt-1 space-y-1">
                <li>service=WFS</li>
                <li>request=GetFeature</li>
                <li>version (e.g., 1.1.0 or 2.0.0)</li>
                <li>typename (layer name)</li>
                <li>outputFormat=application/json (recommended)</li>
              </ul>
            </div>
            {wfsValidation && !wfsValidation.isValid && (
              <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded-md">
                <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-red-700">{wfsValidation.error}</div>
              </div>
            )}
            {wfsValidation && wfsValidation.isValid && <div className="text-xs text-green-600">✓ Valid WFS URL format</div>}
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
                Connecting to WFS...
              </>
            ) : (
              'Connect to WFS'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
