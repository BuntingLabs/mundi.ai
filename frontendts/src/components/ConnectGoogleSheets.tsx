// Copyright Bunting Labs, Inc. 2025

import { AlertTriangle, Loader2 } from 'lucide-react';
import React, { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

// Validate Google Sheets URL client-side
const validateGoogleSheetsUrl = (url: string): { isValid: boolean; error?: string } => {
  if (!url.trim()) {
    return { isValid: false, error: 'URL is required' };
  }

  try {
    const parsedUrl = new URL(url);

    // Check if it's HTTP/HTTPS
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      return { isValid: false, error: 'URL must use HTTP or HTTPS protocol' };
    }

    // Check if it's a Google Sheets URL
    if (!url.includes('docs.google.com/spreadsheets')) {
      return { isValid: false, error: 'Must be a Google Sheets URL (docs.google.com/spreadsheets)' };
    }

    // Check for spreadsheet ID
    const matches = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    if (!matches) {
      return { isValid: false, error: 'Invalid Google Sheets URL format - missing spreadsheet ID' };
    }

    return { isValid: true };
  } catch (_error) {
    return { isValid: false, error: 'Invalid URL format' };
  }
};

// Transform Google Sheets URL to CSV export format
const transformGoogleSheetsUrl = (url: string): string => {
  try {
    // Check if it's a Google Sheets URL
    if (!url.includes('docs.google.com/spreadsheets')) {
      return `CSV:/vsicurl/${url}`;
    }

    // Extract the spreadsheet ID from various Google Sheets URL formats
    const matches = url.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
    if (!matches) {
      throw new Error('Invalid Google Sheets URL format');
    }

    const spreadsheetId = matches[1];

    // Extract the sheet ID (gid) if present in the URL
    let gid = '0'; // default to first sheet
    const gidMatch = url.match(/[#&]gid=([0-9]+)/);
    if (gidMatch) {
      gid = gidMatch[1];
    }

    // Convert to CSV export URL using the proper export format and prefix with CSV: for OGR
    const csvUrl = `https://docs.google.com/spreadsheets/d/${spreadsheetId}/export?format=csv&id=${spreadsheetId}&gid=${gid}`;
    return `CSV:/vsicurl/${csvUrl}`;
  } catch (_error) {
    // If transformation fails, return the original URL with CSV prefix
    return `CSV:/vsicurl/${url}`;
  }
};

interface ConnectGoogleSheetsProps {
  isOpen: boolean;
  onClose: () => void;
  mapId?: string;
  onSuccess?: () => void;
}

export const ConnectGoogleSheets: React.FC<ConnectGoogleSheetsProps> = ({ isOpen, onClose, mapId, onSuccess }) => {
  const [layerName, setLayerName] = useState('');
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheetsValidation, setSheetsValidation] = useState<{ isValid: boolean; error?: string } | null>(null);

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
      setError('Please provide a Google Sheets URL');
      return;
    }

    // Validate Google Sheets URL
    const validation = validateGoogleSheetsUrl(url);
    if (!validation.isValid) {
      setError(validation.error || 'Invalid Google Sheets URL');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Transform Google Sheets URL to CSV export format
      const processedUrl = transformGoogleSheetsUrl(url);

      const response = await fetch(`/api/maps/${mapId}/layers/remote`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: processedUrl,
          name: layerName,
          add_layer_to_map: true,
          source_type: 'sheets',
        }),
      });

      if (response.ok) {
        toast.success('Google Sheets layer added successfully!');
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
    setSheetsValidation(null);
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
          <DialogTitle>Connect to Google Sheets</DialogTitle>
          <DialogDescription>
            Import data from a Google Sheets spreadsheet. The sheet must be publicly accessible or shared with "Anyone with the link can
            view".
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
            <label htmlFor="sheets-url" className="text-sm font-medium">
              Google Sheets URL
            </label>
            <Input
              id="sheets-url"
              placeholder="https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit#gid=0"
              value={url}
              onChange={(e) => {
                const newUrl = e.target.value;
                setUrl(newUrl);
                setError(null);

                // Real-time validation for Google Sheets URL
                if (newUrl.trim()) {
                  const validation = validateGoogleSheetsUrl(newUrl);
                  setSheetsValidation(validation);
                } else {
                  setSheetsValidation(null);
                }
              }}
            />
            <p className="text-xs text-gray-600 dark:text-gray-400">
              Paste the shareable Google Sheets URL. Make sure the sheet is publicly accessible or shared with "Anyone with the link can
              view". The URL should include the gid parameter for the specific sheet.
            </p>
            {sheetsValidation && !sheetsValidation.isValid && (
              <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded-md">
                <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-red-700">{sheetsValidation.error}</div>
              </div>
            )}
            {sheetsValidation && sheetsValidation.isValid && <div className="text-xs text-green-600">✓ Valid Google Sheets URL format</div>}
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
                Connecting to Google Sheets...
              </>
            ) : (
              'Connect to Google Sheets'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
