// Copyright Bunting Labs, Inc. 2025

import { Clock, Plus, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Checkbox } from '@/components/ui/checkbox';
import { useProjects } from '../contexts/ProjectsContext';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from './ui/pagination';
import { Tooltip, TooltipProvider, TooltipTrigger } from './ui/tooltip';

interface MapsListProps {
  hideNewButton?: boolean;
}

export default function MapsList({ hideNewButton = false }: MapsListProps) {
  const {
    projects,
    totalPages,
    totalItems,
    currentPage,
    showDeleted,
    isLoading,
    error,
    setCurrentPage,
    setShowDeleted,
    createProject,
    deleteProject,
  } = useProjects();

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const renderPagination = () => {
    if (totalPages <= 1) return null;

    const getVisiblePages = () => {
      const pages = [];
      const maxVisible = 5;

      if (totalPages <= maxVisible) {
        for (let i = 1; i <= totalPages; i++) {
          pages.push(i);
        }
      } else {
        const start = Math.max(1, currentPage - 2);
        const end = Math.min(totalPages, currentPage + 2);

        for (let i = start; i <= end; i++) {
          pages.push(i);
        }
      }

      return pages;
    };

    const visiblePages = getVisiblePages();

    return (
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              onClick={() => currentPage > 1 && handlePageChange(currentPage - 1)}
              className={currentPage <= 1 ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
            />
          </PaginationItem>

          {visiblePages.map((page) => (
            <PaginationItem key={page}>
              <PaginationLink onClick={() => handlePageChange(page)} isActive={currentPage === page} className="cursor-pointer">
                {page}
              </PaginationLink>
            </PaginationItem>
          ))}

          <PaginationItem>
            <PaginationNext
              onClick={() => currentPage < totalPages && handlePageChange(currentPage + 1)}
              className={currentPage >= totalPages ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    );
  };

  const handleCreateMap = async () => {
    try {
      await createProject();
    } catch (err) {
      // Error handling is managed by the context
      console.error('Failed to create map:', err);
    }
  };

  const handleDeleteMap = async (projectId: string, event: React.MouseEvent) => {
    event.preventDefault(); // Prevent navigation
    event.stopPropagation(); // Stop event bubbling

    try {
      await deleteProject(projectId);
    } catch (err) {
      // Error handling is managed by the context
      console.error('Failed to delete map:', err);
    }
  };

  return (
    <div className="w-full flex flex-col gap-6 p-6 min-w-xl">
      <div className="flex items-center justify-between relative">
        <div className="flex items-center gap-3">
          <div className="flex flex-row items-center gap-2">
            <Checkbox
              checked={showDeleted}
              onCheckedChange={(checked) => {
                setShowDeleted(checked === true);
              }}
            />
            <label className="text-sm font-normal text-gray-300 cursor-pointer">Show recently deleted</label>
          </div>
        </div>

        <div className="absolute left-1/2 transform -translate-x-1/2">
          <h1 className="text-2xl font-bold">
            {showDeleted ? 'Recently Deleted Maps' : 'Your Maps'} <span className="text-gray-400">({totalItems} projects)</span>
          </h1>
        </div>

        {!hideNewButton && (
          <TooltipProvider delayDuration={100}>
            <Tooltip>
              <TooltipTrigger asChild>
                <div>
                  <Button
                    onClick={handleCreateMap}
                    disabled={isLoading}
                    className="bg-[#C1FA3D] hover:bg-[#B8E92B] text-black hover:cursor-pointer"
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    {isLoading ? 'Creating...' : 'New Map'}
                  </Button>
                </div>
              </TooltipTrigger>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {/* Top pagination */}
      {renderPagination()}

      {error ? (
        <Card className="border-red-500 border-2 text-white flex flex-col items-center justify-center p-6">
          <div className="h-8 w-8 mb-2 text-red-500 flex items-center justify-center">
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-red-400">Error Loading Maps</h3>
          <p className="text-sm text-gray-400 text-center mt-1">{error}</p>
          <Button
            onClick={() => {
              // Refetch projects handled by context
            }}
            className="mt-4 bg-[#C1FA3D] hover:bg-[#B8E92B] text-black hover:cursor-pointer"
          >
            Try Again
          </Button>
        </Card>
      ) : isLoading ? (
        <Card className="border-slate-500 text-white flex flex-col items-center justify-center p-6">
          <div className="h-8 w-8 mb-2 text-gray-400 flex items-center justify-center">
            <svg className="animate-spin h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </div>
          <h3 className="text-lg font-medium">Loading Maps...</h3>
          <p className="text-sm text-gray-400 text-center mt-1">Please wait while we fetch your projects</p>
        </Card>
      ) : projects.length === 0 ? (
        <Card className="border-dashed border-2 border-slate-500 text-white flex flex-col items-center justify-center p-6">
          <Plus className="h-8 w-8 mb-2 text-[#e2420d]" />
          <h3 className="text-lg font-medium">No Maps Found</h3>
          <p className="text-sm text-gray-400 text-center mt-1">Create your first map to get started</p>
          {!hideNewButton && (
            <Button
              onClick={handleCreateMap}
              disabled={isLoading}
              className="mt-4 bg-[#C1FA3D] hover:bg-[#B8E92B] text-black hover:cursor-pointer"
            >
              {isLoading ? 'Creating...' : 'Create Your First Map'}
            </Button>
          )}
        </Card>
      ) : (
        <>
          <>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
              {projects.map((project) => (
                <Link to={`/project/${project.id}`} key={project.id}>
                  <div
                    key={project.id}
                    className="relative h-[280px] border border-zinc-300 rounded-md overflow-hidden group cursor-pointer"
                    style={
                      project.soft_deleted_at === null
                        ? {
                            backgroundImage: `url(/api/projects/${project.id}/social.webp)`,
                            backgroundSize: 'cover',
                            backgroundPosition: 'center',
                            backgroundRepeat: 'no-repeat',
                          }
                        : {
                            backgroundImage: 'repeating-linear-gradient(45deg, #374151 0px, #374151 10px, #4b5563 10px, #4b5563 20px)',
                          }
                    }
                  >
                    {/* Dark overlay for better text readability */}
                    <div className="absolute inset-0 bg-black/40 group-hover:bg-black/50 transition-colors" />

                    {/* Delete button - appears on hover */}
                    {project.soft_deleted_at === null && (
                      <button
                        onClick={(e) => handleDeleteMap(project.id, e)}
                        className="absolute top-2 right-2 p-1 bg-red-800 hover:bg-red-700 text-gray-200 hover:text-white rounded-md opacity-0 group-hover:opacity-100 transition-opacity z-10 cursor-pointer"
                        title="Delete map"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}

                    {/* Content overlay */}
                    <div className="relative h-full flex flex-col justify-between p-4 text-white">
                      {/* Header */}
                      <div>
                        <h3 className="text-lg font-semibold line-clamp-2 mb-1">{project.title}</h3>
                      </div>

                      {/* Footer */}
                      <div className="flex items-center justify-between space-x-2">
                        <div className="flex items-center text-xs text-gray-200 text-shadow-md">
                          <Clock className="mr-1 h-3 w-3" />
                          {(() => {
                            const lastEdited = new Date(project.most_recent_version?.last_edited || project.created_on);
                            const now = new Date();
                            const diffMs = now.getTime() - lastEdited.getTime();
                            const diffSec = Math.floor(diffMs / 1000);
                            const diffMin = Math.floor(diffSec / 60);
                            const diffHour = Math.floor(diffMin / 60);
                            const diffDay = Math.floor(diffHour / 24);

                            let value, unit;
                            if (diffSec < 60) {
                              value = -diffSec;
                              unit = 'second';
                            } else if (diffMin < 60) {
                              value = -diffMin;
                              unit = 'minute';
                            } else if (diffHour < 24) {
                              value = -diffHour;
                              unit = 'hour';
                            } else {
                              value = -diffDay;
                              unit = 'day';
                            }

                            const rtf = new Intl.RelativeTimeFormat(undefined, {
                              numeric: 'auto',
                            });
                            return `Last edited ${rtf.format(value, unit as Intl.RelativeTimeFormatUnit)}`;
                          })()}
                        </div>

                        <Button size="sm" asChild className="bg-[#C1FA3D] hover:bg-[#B8E92B] text-black">
                          Open
                        </Button>
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </>
        </>
      )}

      {/* Bottom pagination */}
      {renderPagination()}

      {/* Add CSS to ensure consistent image alignment */}
      <style>{`
        [data-map-item] {
          display: flex;
          flex-direction: column;
        }

        [data-map-item] > div {
          height: 100%;
        }
      `}</style>
    </div>
  );
}
