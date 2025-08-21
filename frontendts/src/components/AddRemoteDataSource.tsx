// Copyright Bunting Labs, Inc. 2025

import { AlertTriangle, Loader2 } from 'lucide-react';
import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

interface AddRemoteDataSourceProps {
  isOpen: boolean;
  onClose: () => void;
  mapId?: string;
  onSuccess?: () => void;
}

export const AddRemoteDataSource: React.FC<AddRemoteDataSourceProps> = ({ isOpen, onClose, mapId, onSuccess }) => {
  const [form, setForm] = useState({
    layerName: '',
    url: '',
    layerType: 'vector' as 'vector' | 'raster',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConnect = async () => {
    if (!mapId) {
      toast.error('No map ID available');
      return;
    }

    if (!form.layerName.trim()) {
      setError('Please provide a layer name');
      return;
    }

    if (!form.url.trim()) {
      setError('Please provide a URL');
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
          url: form.url,
          name: form.layerName,
          add_layer_to_map: true,
          source_type: form.layerType,
        }),
      });

      if (response.ok) {
        toast.success('Remote layer added successfully!');
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
    setForm({
      layerName: '',
      url: '',
      layerType: 'vector',
    });
    setError(null);
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
          <DialogTitle>Add Remote Layer</DialogTitle>
          <DialogDescription>
            Add a layer from a remote URL. Supports various formats including Cloud Optimized GeoTIFFs and vector data.
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
              value={form.layerName}
              onChange={(e) => {
                setForm((prev) => ({
                  ...prev,
                  layerName: e.target.value,
                }));
                setError(null);
              }}
            />
          </div>

          {/* Layer Type Toggle */}
          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={form.layerType === 'vector' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setForm((prev) => ({ ...prev, layerType: 'vector' }))}
              className="hover:cursor-pointer"
            >
              Vector
            </Button>
            <Button
              type="button"
              variant={form.layerType === 'raster' ? 'default' : 'outline'}
              size="sm"
              onClick={() => setForm((prev) => ({ ...prev, layerType: 'raster' }))}
              className="hover:cursor-pointer"
            >
              Raster
            </Button>
          </div>

          {form.layerType === 'vector' ? (
            <div className="space-y-2">
              <label htmlFor="vector-url" className="text-sm font-medium">
                Vector Layer URL
              </label>
              <Input
                id="vector-url"
                placeholder="https://example.com/data.geojson or https://example.com/data.fgb"
                value={form.url}
                onChange={(e) => {
                  setForm((prev) => ({
                    ...prev,
                    url: e.target.value,
                  }));
                  setError(null);
                }}
              />
              <p className="text-xs text-gray-600 dark:text-gray-400">Supports GeoJSON, FlatGeobuf, and other vector formats</p>
            </div>
          ) : (
            <div className="space-y-2">
              <label htmlFor="raster-url" className="text-sm font-medium">
                Raster Layer URL
              </label>
              <Input
                id="raster-url"
                placeholder="https://example.com/data.tif (Cloud Optimized GeoTIFF)"
                value={form.url}
                onChange={(e) => {
                  setForm((prev) => ({
                    ...prev,
                    url: e.target.value,
                  }));
                  setError(null);
                }}
              />
              <p className="text-xs text-gray-600 dark:text-gray-400">Supports Cloud Optimized GeoTIFFs (COGs)</p>
            </div>
          )}

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
                Adding Layer...
              </>
            ) : (
              'Add Layer'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
