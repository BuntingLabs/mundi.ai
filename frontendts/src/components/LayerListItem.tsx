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

import { Eye, EyeOff } from 'lucide-react';
import React from 'react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';

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
  title,
}) => {
  let liClassName = '';

  if (displayAsDiff) {
    if (status === 'added') {
      liClassName += ' bg-green-100 dark:bg-green-900 hover:bg-green-200 dark:hover:bg-green-800';
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

  const truncatedName = name.length > 26 ? name.slice(0, 26) + '...' : name;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className={`${liClassName} flex items-center justify-between px-2 py-1 gap-2 cursor-pointer group w-full text-left ${className}`}
          title={title}
          onClick={(e) => {
            console.log('LayerListItem clicked:', { name, e });
            onClick?.(e);
          }}
        >
          <div className="flex items-center gap-2">
            <span className={`font-medium truncate ${nameClassName}`} title={name}>
              {truncatedName}
            </span>
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
            <div className="w-5 h-5 flex-shrink-0 relative">
              <div className="group-hover:hidden">{legendSymbol}</div>
              <span
                role="button"
                tabIndex={0}
                aria-label={isVisible ? 'Hide layer' : 'Show layer'}
                className="hidden group-hover:flex items-center justify-center w-5 h-5 rounded cursor-pointer hover:bg-slate-200 dark:hover:bg-gray-500"
                onPointerDown={(e) => {
                  // Prevent triggering the parent DropdownMenuTrigger
                  e.preventDefault();
                  e.stopPropagation();
                }}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onToggleVisibility?.(layerId);
                }}
              >
                {isVisible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              </span>
            </div>
          </div>
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
  );
};
