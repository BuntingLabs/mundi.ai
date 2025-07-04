// Copyright Bunting Labs, Inc. 2025

import { useParams, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Database, Loader2, ArrowLeft, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import MermaidComponent from "@/components/MermaidComponent";
import { useEffect, useState, useRef } from "react";
import { Scrollspy } from "@/components/ui/scrollspy";
import { ScrollArea } from "@/components/ui/scroll-area";

interface PostgresConnection {
  connection_id: string;
  friendly_name?: string;
  connection_name?: string;
}

interface NavigationItem {
  id: string;
  label: string;
  level: number;
}

const PostGISDocumentation = () => {
  const { connectionId } = useParams<{ connectionId: string }>();
  const navigate = useNavigate();
  const scrollAreaRef = useRef<HTMLDivElement | null>(null);

  const [documentation, setDocumentation] = useState<string | null>(null);
  const [connectionName, setConnectionName] = useState<string>("");
  const [projectId, setProjectId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [navigationItems, setNavigationItems] = useState<NavigationItem[]>([]);

  useEffect(() => {
    if (connectionId) {
      fetchDocumentation();
    }
  }, [connectionId]);

  // Extract headings from markdown content
  useEffect(() => {
    if (documentation) {
      const headingRegex = /^(#{1,6})\s+(.+)$/gm;
      const headings: NavigationItem[] = [];
      let match;

      while ((match = headingRegex.exec(documentation)) !== null) {
        const level = match[1].length;
        const text = match[2].trim();
        const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

        headings.push({
          id,
          label: text,
          level
        });
      }

      setNavigationItems(headings);
    }
  }, [documentation]);

  const fetchDocumentation = async () => {
    setLoading(true);
    setError(null);

    try {
      // First, we need to find which project this connection belongs to
      const projectsResponse = await fetch('/api/projects/');
      if (!projectsResponse.ok) {
        throw new Error('Failed to fetch projects');
      }
      const projectsData = await projectsResponse.json();

      // Search through all projects to find the one containing this connection
      let foundProjectId = '';
      let foundConnectionName = '';

      for (const project of projectsData.projects) {
        // Get the full project details which includes postgres_connections
        const projectResponse = await fetch(`/api/projects/${project.id}`);
        if (projectResponse.ok) {
          const projectDetails = await projectResponse.json();
          const connection = projectDetails.postgres_connections?.find((c: PostgresConnection) => c.connection_id === connectionId);
          if (connection) {
            foundProjectId = project.id;
            foundConnectionName = connection.friendly_name || connection.connection_name || 'Database';
            break;
          }
        }
      }

      if (!foundProjectId) {
        throw new Error('Connection not found in any project');
      }

      setProjectId(foundProjectId);
      setConnectionName(foundConnectionName);

      // Now fetch the documentation
      const docResponse = await fetch(`/api/projects/${foundProjectId}/postgis-connections/${connectionId}/documentation`);
      if (!docResponse.ok) {
        throw new Error(`Failed to fetch documentation: ${docResponse.statusText}`);
      }
      const docData = await docResponse.json();
      setDocumentation(docData.documentation);
      if (docData.friendly_name) {
        setConnectionName(docData.friendly_name);
      }
    } catch (err) {
      console.error('Error fetching database documentation:', err);
      setError(err instanceof Error ? err.message : 'Failed to load documentation');
      setDocumentation(null);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (!connectionId || !projectId) return;

    setIsRegenerating(true);
    setError(null);

    try {
      const response = await fetch(`/api/projects/${projectId}/postgis-connections/${connectionId}/regenerate-documentation`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`Failed to regenerate documentation: ${response.statusText}`);
      }

      // Wait a moment and then refetch the documentation
      setTimeout(() => {
        fetchDocumentation();
        setIsRegenerating(false);
      }, 2000);
    } catch (err) {
      console.error('Error regenerating database documentation:', err);
      setError(err instanceof Error ? err.message : 'Failed to regenerate documentation');
      setIsRegenerating(false);
    }
  };

  const fallbackContent = `
Documentation is being generated for this database. Please check back in a few moments.

If documentation generation fails, this indicates the database connection details or the database structure couldn't be analyzed automatically.
`;

  return (
    <div className="flex flex-col h-screen bg-background w-full">
      {/* Header */}
      <div className="border-b">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="flex items-center gap-2 hover:cursor-pointer"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Map
            </Button>
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              <h1 className="text-xl font-semibold">{connectionName || 'Database Documentation'}</h1>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRegenerate}
            disabled={isRegenerating || loading}
            className="flex items-center gap-2 hover:cursor-pointer"
          >
            {isRegenerating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            {isRegenerating ? 'Regenerating...' : 'Regenerate'}
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <div className="flex h-full">
          {/* Main Content */}
          <div className="flex-1 overflow-y-auto">
            <ScrollArea className="h-full" ref={scrollAreaRef}>
              <div className="p-8">
                <div className="max-w-4xl mx-auto">
                  {loading && (
                    <div className="flex items-center justify-center p-8">
                      <Loader2 className="h-6 w-6 animate-spin mr-2" />
                      <span>Loading database documentation...</span>
                    </div>
                  )}

                  {error && (
                    <div className="p-4 border border-red-500 rounded-lg mb-4">
                      <p className="text-red-500">Error loading documentation: {error}</p>
                    </div>
                  )}

                  {!loading && !error && (
                    <div className="prose prose-sm prose-invert max-w-none">
                      <ReactMarkdown
                        components={{
                          code(props) {
                            const { className, children, ...rest } = props;
                            const match = /language-(\w+)/.exec(className || '');
                            const language = match ? match[1] : '';

                            if (language === 'mermaid') {
                              return (
                                <div className="bg-muted/20 mx-auto my-4">
                                  <MermaidComponent chart={String(children)} />
                                </div>
                              );
                            }

                            return (
                              <code className={className} {...rest}>
                                {children}
                              </code>
                            );
                          },
                          h1(props) {
                            const { children, ...rest } = props;
                            const text = String(children);
                            const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                            return <h1 id={id} {...rest}>{children}</h1>;
                          },
                          h2(props) {
                            const { children, ...rest } = props;
                            const text = String(children);
                            const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                            return <h2 id={id} {...rest}>{children}</h2>;
                          },
                          h3(props) {
                            const { children, ...rest } = props;
                            const text = String(children);
                            const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                            return <h3 id={id} {...rest}>{children}</h3>;
                          },
                          h4(props) {
                            const { children, ...rest } = props;
                            const text = String(children);
                            const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                            return <h4 id={id} {...rest}>{children}</h4>;
                          },
                          h5(props) {
                            const { children, ...rest } = props;
                            const text = String(children);
                            const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                            return <h5 id={id} {...rest}>{children}</h5>;
                          },
                          h6(props) {
                            const { children, ...rest } = props;
                            const text = String(children);
                            const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                            return <h6 id={id} {...rest}>{children}</h6>;
                          }
                        }}
                      >
                        {documentation || fallbackContent}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>

              <div className="border-l-4 border-blue-500 bg-blue-50 dark:bg-blue-950 p-4 mb-6 mx-8">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-blue-400 dark:text-blue-300" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-blue-700 dark:text-blue-200">
                      <strong>Have questions?</strong> Open any map that is connected to this PostGIS database, and Kue will be able to answer questions based on this article.
                    </p>
                  </div>
                </div>
              </div>
            </ScrollArea>
          </div>

          {/* Navigation Sidebar - only show if we have navigation items */}
          {navigationItems.length > 0 && !loading && !error && (
            <div className="w-64 border-l bg-muted/20 p-4 overflow-y-auto">
              <h3 className="font-semibold mb-4 text-sm text-muted-foreground uppercase tracking-wide">
                Table of Contents
              </h3>
              <Scrollspy offset={50} targetRef={scrollAreaRef} className="flex flex-col gap-1">
                {navigationItems.map((item) => (
                  <Button
                    key={item.id}
                    variant="ghost"
                    size="sm"
                    data-scrollspy-anchor={item.id}
                    className={`
                      justify-start text-left h-auto py-2 px-3 whitespace-normal
                      data-[active=true]:bg-accent data-[active=true]:text-accent-foreground
                      ${item.level === 1 ? 'font-medium' : ''}
                      ${item.level === 2 ? 'ml-3 text-sm' : ''}
                      ${item.level === 3 ? 'ml-6 text-sm' : ''}
                      ${item.level >= 4 ? 'ml-9 text-xs' : ''}
                    `}
                  >
                    {item.label}
                  </Button>
                ))}
              </Scrollspy>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PostGISDocumentation;