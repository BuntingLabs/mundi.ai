// Copyright Bunting Labs, Inc. 2025

import { cogProtocol } from '@geomatico/maplibre-cog-protocol';
import { ApiKeys } from '@mundi/ee';
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { useEffect } from 'react';
import * as reactRouterDom from 'react-router-dom';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarProvider } from '@/components/ui/sidebar';
import { Toaster } from '@/components/ui/sonner';
import MapsList from './components/MapsList';
import ProjectView from './components/ProjectView';
import { ProjectsProvider } from './contexts/ProjectsContext';
import NotFound from './pages/NotFound';
import PostGISDocumentation from './pages/PostGISDocumentation';
import './App.css';
import { Routes as EERoutes, OptionalAuth, Provider, RequireAuth } from '@mundi/ee';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense } from 'react';

const websiteDomain = import.meta.env.VITE_WEBSITE_DOMAIN;
if (!websiteDomain) {
  throw new Error('VITE_WEBSITE_DOMAIN is not defined. Please set it in your .env file or build environment.');
}

function AppContent() {
  useEffect(() => {
    const protocol = new Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);
    maplibregl.addProtocol('cog', cogProtocol);
    return () => {
      maplibregl.removeProtocol('pmtiles');
      maplibregl.removeProtocol('cog');
    };
  }, []);

  return (
    <BrowserRouter>
      <SidebarProvider className="z-50">
        <ProjectsProvider>
          <AppSidebar />

          <Routes>
            {EERoutes(reactRouterDom)}
            {/* App Routes */}
            <Route
              path="/"
              element={
                <RequireAuth>
                  <MapsList />
                </RequireAuth>
              }
            />
            <Route
              path="/project/:projectId/:versionIdParam?"
              element={
                <OptionalAuth>
                  <ProjectView />
                </OptionalAuth>
              }
            />
            <Route
              path="/postgis/:connectionId"
              element={
                <RequireAuth>
                  <PostGISDocumentation />
                </RequireAuth>
              }
            />
            <Route
              path="/settings/api-keys"
              element={
                <Suspense fallback={<div>Loading...</div>}>
                  <RequireAuth>
                    <ApiKeys />
                  </RequireAuth>
                </Suspense>
              }
            />

            <Route path="*" element={<NotFound />} />
          </Routes>
        </ProjectsProvider>
      </SidebarProvider>
    </BrowserRouter>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Provider>
        <AppContent />
        <Toaster />
      </Provider>
    </QueryClientProvider>
  );
}

export default App;
