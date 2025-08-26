// Copyright Bunting Labs, Inc. 2025

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MapLayer } from '@/lib/types';

type AttributeData = {
  data: Array<{
    id: string;
    attributes: Record<string, any>;
  }>;
  offset: number;
  limit: number;
  has_more: boolean;
  total_count: number | null;
  field_names: string[];
};

interface AttributeTableProps {
  layer: MapLayer;
  isOpen: boolean;
  onClose: () => void;
}

const PAGE_SIZE = 100;

const fetchLayerAttributes = async (layerId: string, offset: number): Promise<AttributeData> => {
  const response = await fetch(`/api/layer/${layerId}/attributes?offset=${offset}&limit=${PAGE_SIZE}`);

  if (!response.ok) {
    throw new Error('Failed to fetch layer data');
  }

  return response.json();
};

export default function AttributeTable({ layer, isOpen, onClose }: AttributeTableProps) {
  const [currentOffset, setCurrentOffset] = useState(0);

  // Reset offset when layer changes or dialog opens
  // biome-ignore lint/correctness/useExhaustiveDependencies: We want to reset when layer changes
  useEffect(() => {
    if (isOpen) {
      setCurrentOffset(0);
    }
  }, [isOpen, layer.id]);

  // Use React Query with proper cache keys
  const { data, isLoading, error, isPlaceholderData } = useQuery({
    queryKey: ['layer-attributes', layer.id, currentOffset],
    queryFn: () => fetchLayerAttributes(layer.id, currentOffset),
    enabled: isOpen, // Only fetch when dialog is open
    staleTime: 5 * 60 * 1000, // Data is fresh for 5 minutes
    retry: 2,
    placeholderData: keepPreviousData, // Keep previous data while loading new data with different keys
  });

  // Handle escape key to close dialog
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  const handlePreviousPage = () => {
    const newOffset = Math.max(0, currentOffset - PAGE_SIZE);
    setCurrentOffset(newOffset);
  };

  const handleNextPage = () => {
    const newOffset = currentOffset + PAGE_SIZE;
    setCurrentOffset(newOffset);
  };

  const canGoPrevious = currentOffset > 0;
  const canGoNext = data?.has_more === true;

  const totalFeatures = data?.total_count || layer.feature_count;
  const currentStart = currentOffset + 1;
  const currentEnd = Math.min(currentOffset + PAGE_SIZE, currentStart + (data?.data.length || 0) - 1);

  return (
    <Dialog open={isOpen} onOpenChange={() => onClose()}>
      <DialogContent className="sm:max-w-[90vw] md:max-w-[1000px] max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="font-semibold text-base">
            Attributes: {layer.name}
            <span className="text-muted-foreground ml-2">({totalFeatures} features)</span>
            {isPlaceholderData && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground ml-2 inline" />}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-2 flex-1 min-h-0">
          {/* Pagination controls */}
          <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handlePreviousPage} disabled={!canGoPrevious || isPlaceholderData}>
                <ChevronLeft className="h-4 w-4" />
                Previous
              </Button>
              <Button variant="outline" size="sm" onClick={handleNextPage} disabled={!canGoNext || isPlaceholderData}>
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            {data && (
              <span className="text-sm text-muted-foreground">
                Showing {currentStart}-{currentEnd} of {totalFeatures}
              </span>
            )}
          </div>

          {/* Table display with sticky header */}
          <div className="border border-border rounded-md flex-1 overflow-auto">
            {error ? (
              <div className="flex items-center justify-center h-32 text-destructive">
                <span>Failed to load attributes: {error.message}</span>
              </div>
            ) : data ? (
              <table className={`w-full text-sm relative ${isPlaceholderData ? 'opacity-50' : ''}`}>
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    <th className="p-2 text-left font-medium text-muted-foreground sticky top-0 bg-muted/50 border-b border-border min-w-[80px]">
                      ID
                    </th>
                    {data.field_names.map((fieldName, i) => (
                      <th
                        key={i}
                        className="p-2 text-left font-medium text-muted-foreground sticky top-0 bg-muted/50 border-b border-border whitespace-nowrap"
                      >
                        {fieldName}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.data.map((feature) => (
                    <tr key={feature.id} className="border-b border-border hover:bg-muted/30">
                      <td className="p-2 text-muted-foreground text-xs font-mono">{feature.id}</td>
                      {data.field_names.map((fieldName, j) => (
                        <td key={j} className="p-2 whitespace-nowrap">
                          {feature.attributes[fieldName] !== null && feature.attributes[fieldName] !== undefined ? (
                            String(feature.attributes[fieldName])
                          ) : (
                            <span className="text-muted-foreground italic">null</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : isLoading ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : null}
          </div>

          {/* Bottom pagination info */}
          {data && (
            <div className="text-xs text-muted-foreground text-center py-2">
              {data.field_names.length} field{data.field_names.length !== 1 ? 's' : ''} • Page {Math.floor(currentOffset / PAGE_SIZE) + 1}
              {data.total_count && ` of ${Math.ceil(data.total_count / PAGE_SIZE)}`}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
