// Copyright Bunting Labs, Inc. 2025
import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from "react-router-dom";

import SuperTokens, { SuperTokensWrapper } from "supertokens-auth-react";
import { getSuperTokensRoutesForReactRouterDom } from "supertokens-auth-react/ui";
import { EmailPasswordPreBuiltUI } from "supertokens-auth-react/recipe/emailpassword/prebuiltui";
import EmailPassword from "supertokens-auth-react/recipe/emailpassword";
import Session, { SessionAuth } from "supertokens-auth-react/recipe/session";
import EmailVerification from "supertokens-auth-react/recipe/emailverification";
import { EmailVerificationPreBuiltUI } from "supertokens-auth-react/recipe/emailverification/prebuiltui";
import * as reactRouterDom from "react-router-dom";

import { Toaster } from "@/components/ui/sonner"
import { SidebarProvider } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"

import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import { cogProtocol } from '@geomatico/maplibre-cog-protocol';

import MapsList from './components/MapsList';
import ProjectView from './components/ProjectView';
import PostGISDocumentation from './pages/PostGISDocumentation';
import './App.css'

const websiteDomain = import.meta.env.VITE_WEBSITE_DOMAIN;
if (!websiteDomain) {
  throw new Error("VITE_WEBSITE_DOMAIN is not defined. Please set it in your .env file or build environment.");
}

const emailVerificationMode = import.meta.env.VITE_EMAIL_VERIFICATION;
if (emailVerificationMode !== 'require' && emailVerificationMode !== 'disable') {
  throw new Error("VITE_EMAIL_VERIFICATION must be either 'require' or 'disable'");
}
const emailVerificationEnabled = emailVerificationMode === 'require';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const recipeList: any[] = [EmailPassword.init(), Session.init()];
if (emailVerificationEnabled) {
  recipeList.push(EmailVerification.init({ mode: "REQUIRED" }));
}

SuperTokens.init({
  appInfo: {
    appName: "Mundi",
    apiDomain: websiteDomain,
    websiteDomain: websiteDomain,
    apiBasePath: "/supertokens",
    websiteBasePath: "/auth",
  },
  recipeList,
  style: `
  [data-supertokens~="container"] {
    font-family: "Geist", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }`
});

import { useState } from 'react';
import { ProjectState } from './lib/types';

function AppContent() {
  const [projectState, setProjectState] = useState<ProjectState>({ type: 'not_logged_in' });
  const sessionContext = Session.useSessionContext();

  useEffect(() => {
    const protocol = new Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);
    maplibregl.addProtocol('cog', cogProtocol);
    return () => {
      maplibregl.removeProtocol("pmtiles");
      maplibregl.removeProtocol("cog");
    };
  }, []);

  useEffect(() => {
    if (sessionContext.loading) {
      return;
    }

    if (!sessionContext.doesSessionExist) {
      setProjectState({ type: 'not_logged_in' });
      return;
    }

    setProjectState({ type: 'loading' });

    const fetchProjects = async () => {
      try {
        const response = await fetch('/api/projects/');
        if (!response.ok) {
          throw new Error('Failed to fetch projects');
        }
        const data = await response.json();
        setProjectState({ type: 'loaded', projects: data.projects || [] });
      } catch (error) {
        console.error('Error fetching projects:', error);
        setProjectState({ type: 'loaded', projects: [] });
      }
    };

    fetchProjects();
  }, [sessionContext]);

  return (
    <BrowserRouter>
      <SidebarProvider className="z-50">
        <AppSidebar projects={projectState} />

        <Routes>
          {/* SuperTokens Routes for authentication UI */}
          {getSuperTokensRoutesForReactRouterDom(reactRouterDom, emailVerificationEnabled ? [EmailPasswordPreBuiltUI, EmailVerificationPreBuiltUI] : [EmailPasswordPreBuiltUI])}

          {/* App Routes */}
          <Route path="/" element={
            <SessionAuth>
              <MapsList />
            </SessionAuth>
          } />
          <Route path="/project/:projectId/:versionIdParam?" element={
            <SessionAuth>
              <ProjectView />
            </SessionAuth>
          } />
          <Route path="/postgis/:connectionId" element={
            <SessionAuth>
              <PostGISDocumentation />
            </SessionAuth>
          } />
        </Routes>
      </SidebarProvider>
    </BrowserRouter>
  );
}

function App() {
  return (
    <SuperTokensWrapper>
      <AppContent />
      <Toaster />
    </SuperTokensWrapper>
  )
}

export default App