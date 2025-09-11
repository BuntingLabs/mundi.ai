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

import { Eye, EyeOff, GripVertical, Loader2, MoreHorizontal } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';

interface DropdownAction {
  label: string;
  action: (layerId: string) => void;
  disabled?: boolean;
}

interface LayerListItemProps {
  name: string;
  nameClassName?: string;
  status?: 'added' | 'removed' | 'edited' | 'existing';
  isActive?: boolean;
  progressBar?: number | null;
  hoverText?: string;
  normalText?: string;
  legendSymbol?: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  className?: string;
  displayAsDiff?: boolean;
  layerId: string;
  dropdownActions?: {
    [key: string]: DropdownAction;
  };
  isVisible?: boolean;
  onToggleVisibility?: (layerId: string) => void;
  onRename?: (layerId: string, newName: string) => void;
  title?: string;
}

export const LayerListItem: React.FC<LayerListItemProps> = ({
  name,
  nameClassName = '',
  status = 'existing',
  isActive = false,
  progressBar = null,
  hoverText,
  normalText,
  legendSymbol,
  onClick,
  className = '',
  displayAsDiff = false,
  layerId,
  dropdownActions = {},
  isVisible = true,
  onToggleVisibility,
  onRename,
  title,
}) => {
  const [nameValue, setNameValue] = useState(name);
  const [isDebouncing, setIsDebouncing] = useState(false);
  const debounceTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const debouncedSave = useCallback(
    (value: string) => {
      const trimmedValue = value.trim();

      if (trimmedValue && trimmedValue !== name && onRename) {
        onRename(layerId, trimmedValue);
      }
      setIsDebouncing(false);
    },
    [name, onRename, layerId],
  );

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setNameValue(newValue);

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    setIsDebouncing(true);

    debounceTimeoutRef.current = setTimeout(() => {
      debouncedSave(newValue);
    }, 1000);
  };

  // Update local name when prop changes
  useEffect(() => {
    setNameValue(name);
  }, [name]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, []);
  let liClassName = '';

  if (displayAsDiff) {
    if (status === 'added') {
      liClassName += ' bg-green-900 hover:bg-green-800';
    } else if (status === 'removed') {
      liClassName += ' bg-red-100 dark:bg-red-900 hover:bg-red-200 dark:hover:bg-red-800';
    } else if (status === 'edited') {
      liClassName += ' bg-yellow-100 dark:bg-yellow-800 hover:bg-yellow-200 dark:hover:bg-yellow-700';
    } else {
      liClassName += ' hover:bg-slate-100 dark:hover:bg-gray-600 dark:focus:bg-gray-600';
    }
  } else {
    liClassName += ' hover:bg-slate-100 dark:hover:bg-gray-600 dark:focus:bg-gray-600';
  }

  if (isActive) {
    liClassName += ' animate-pulse';
  }

  return (
    <div className={`${liClassName} flex items-center px-2 py-1 gap-2 group w-full ${className}`} title={title}>
      <div className="w-4 h-4 flex-shrink-0 flex items-center justify-center">
        <GripVertical className="w-3 h-3 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity cursor-grab" />
      </div>

      <div className="flex items-center gap-2 flex-1">
        {onRename ? (
          <>
            <Input
              value={nameValue}
              onChange={handleNameChange}
              className={`border-0 rounded-none !bg-transparent p-0 h-auto !text-sm font-medium focus-visible:ring-0 focus-visible:ring-offset-0 shadow-none outline-none flex-1 ${nameClassName}`}
              title={name}
            />
            {isDebouncing && <Loader2 className="h-3 w-3 animate-spin text-gray-400" />}
          </>
        ) : (
          <span className={`font-medium truncate ${nameClassName}`} title={name}>
            {nameValue.length > 26 ? nameValue.slice(0, 26) + '...' : nameValue}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {progressBar !== null && (
          <div className="w-12 h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300 ease-out"
              style={{ width: `${Math.max(0, Math.min(100, progressBar * 100))}%` }}
            />
          </div>
        )}
        {(hoverText || normalText) && (
          <span className="text-xs text-slate-500 dark:text-gray-400">
            {hoverText && normalText ? (
              <>
                <span className="group-hover:hidden">{normalText}</span>
                <span className="hidden group-hover:inline">{hoverText}</span>
              </>
            ) : (
              hoverText || normalText
            )}
          </span>
        )}
        <div className="flex items-center gap-1">
          <div className="w-5 h-5 flex-shrink-0 relative">
            <div className="absolute inset-0 flex items-center justify-center group-hover:hidden">{legendSymbol}</div>
            <button
              className="absolute inset-0 flex items-center justify-center rounded cursor-pointer hover:bg-slate-200 dark:hover:bg-gray-500 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={(e) => {
                e.stopPropagation();
                onToggleVisibility?.(layerId);
              }}
              aria-label={isVisible ? 'Hide layer' : 'Show layer'}
            >
              {isVisible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
            </button>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="w-5 h-5 flex items-center justify-center rounded cursor-pointer opacity-0 group-hover:opacity-100 transition-all hover:bg-slate-200 dark:hover:bg-gray-500"
                onClick={(e) => {
                  e.stopPropagation();
                  onClick?.(e);
                }}
              >
                <MoreHorizontal className="w-4 h-4 text-gray-400 hover:text-white transition-colors" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {Object.entries(dropdownActions).map(([key, actionConfig]) => (
                <DropdownMenuItem
                  key={key}
                  disabled={actionConfig.disabled}
                  onClick={() => actionConfig.action(layerId)}
                  className="border-transparent hover:border-gray-600 hover:cursor-pointer border"
                >
                  {actionConfig.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  );
};
