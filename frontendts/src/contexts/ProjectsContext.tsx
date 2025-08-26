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

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, ReactNode, useContext, useState } from 'react';
import { MapProject } from '../lib/types';

interface ProjectsContextValue {
  // Pagination state
  currentPage: number;
  showDeleted: boolean;
  setCurrentPage: (page: number) => void;
  setShowDeleted: (show: boolean) => void;

  // Data and loading states
  projects: MapProject[];
  totalPages: number;
  totalItems: number;
  isLoading: boolean;
  error: string | null;

  // Actions
  createProject: () => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  refetchProjects: () => void;

  // All projects for sidebar (recent projects)
  allProjects: MapProject[];
  allProjectsLoading: boolean;
}

const ProjectsContext = createContext<ProjectsContextValue | undefined>(undefined);

interface ProjectsProviderProps {
  children: ReactNode;
}

export function ProjectsProvider({ children }: ProjectsProviderProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [showDeleted, setShowDeleted] = useState(false);
  const queryClient = useQueryClient();

  // Query for paginated projects (main list)
  const {
    data: paginatedData,
    isLoading,
    error: queryError,
    refetch: refetchProjects,
  } = useQuery({
    queryKey: ['projects', currentPage, showDeleted],
    queryFn: async () => {
      const response = await fetch(`/api/projects/?page=${currentPage}&limit=12&include_deleted=${showDeleted}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch projects: ${response.status} ${response.statusText}`);
      }
      return response.json();
    },
  });

  // Query for all projects (for sidebar recent projects)
  const { data: allProjectsData, isLoading: allProjectsLoading } = useQuery({
    queryKey: ['projects', 'all'],
    queryFn: async () => {
      const response = await fetch('/api/projects/');
      if (!response.ok) {
        throw new Error(`Failed to fetch all projects: ${response.status} ${response.statusText}`);
      }
      return response.json();
    },
  });

  // Mutation for creating projects
  const createProjectMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch('/api/maps/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: 'New Map',
          description: '',
          project: {
            layers: [],
          },
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create map');
      }

      return response.json();
    },
    onSuccess: () => {
      // Invalidate and refetch both queries
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  // Mutation for deleting projects
  const deleteProjectMutation = useMutation({
    mutationFn: async (projectId: string) => {
      const response = await fetch(`/api/projects/${projectId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete map');
      }

      return response.json();
    },
    onSuccess: () => {
      // Invalidate and refetch both queries
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  const value: ProjectsContextValue = {
    currentPage,
    showDeleted,
    setCurrentPage: (page: number) => {
      setCurrentPage(page);
    },
    setShowDeleted: (show: boolean) => {
      setShowDeleted(show);
      setCurrentPage(1); // Reset to first page when changing filter
    },

    projects: paginatedData?.projects || [],
    totalPages: paginatedData?.total_pages || 1,
    totalItems: paginatedData?.total_items || 0,
    isLoading,
    error: queryError instanceof Error ? queryError.message : null,

    createProject: async () => {
      await createProjectMutation.mutateAsync();
    },
    deleteProject: async (projectId: string) => {
      await deleteProjectMutation.mutateAsync(projectId);
    },
    refetchProjects: () => {
      refetchProjects();
    },

    allProjects: allProjectsData?.projects || [],
    allProjectsLoading,
  };

  return <ProjectsContext.Provider value={value}>{children}</ProjectsContext.Provider>;
}

export function useProjects() {
  const context = useContext(ProjectsContext);
  if (context === undefined) {
    throw new Error('useProjects must be used within a ProjectsProvider');
  }
  return context;
}
