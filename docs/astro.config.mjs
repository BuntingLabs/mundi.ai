// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';
import sitemap from '@astrojs/sitemap';
import starlightOpenAPI, { openAPISidebarGroups } from 'starlight-openapi';
import starlightSidebarTopics from 'starlight-sidebar-topics';
import starlightLinksValidator from 'starlight-links-validator';
import starlightThemeRapide from 'starlight-theme-rapide'

// https://astro.build/config
export default defineConfig({
	site: 'https://docs.mundi.ai',
	integrations: [
		starlight({
			title: 'Mundi GIS Documentation',
			logo: {
				light: './src/assets/Mundi-light.svg',
				dark: './src/assets/Mundi-dark.svg',
				replacesTitle: true,
			},
			favicon: '/favicon-light.svg',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/BuntingLabs/mundi.ai' },
				{ icon: 'discord', label: 'Discord', href: 'https://discord.gg/V63VbgH8dT' }
			],
			// Set English as the default language for this site.
			defaultLocale: 'root',
			locales: {
				// English docs in `src/content/docs/` (root)
				root: {
					label: 'English',
					lang: 'en',
				},
			},
			plugins: [
				starlightSidebarTopics([
					{
						label: 'Documentation',
						icon: 'open-book',
						link: '/',
						items: [
							{
								label: 'Getting started',
								items: [
									{ label: 'Making your first map', slug: 'getting-started/making-your-first-map' },
									{ label: 'Uploading files', slug: 'getting-started/uploading-files' },
									{ label: 'ESRI Feature Server', slug: 'getting-started/esri-feature-server' },
									{ label: 'OGC WFS', slug: 'getting-started/add-ogc-wfs-web-feature-service' },
									{ label: 'Google Sheets', slug: 'getting-started/google-sheets' },
								],
							},
							{
								label: 'Spatial databases',
								items: [
									{ label: 'Connecting to PostGIS', slug: 'spatial-databases/connecting-to-postgis' },
									{ label: 'Querying and styling from SQL', slug: 'spatial-databases/querying-and-styling-from-sql' },
								],
							},
							{
								label: 'Guides',
								items: [
									{ label: 'Geoprocessing from QGIS', slug: 'guides/geoprocessing-from-qgis' },
									{ label: 'Visualizing point clouds', slug: 'guides/visualizing-point-clouds-las-laz' },
									{ label: 'Switching basemaps', slug: 'guides/switching-basemaps-satellite-or-traditional-vector' },
									{ label: 'Embedding into websites', slug: 'guides/embedding-maps-into-websites' },
									{ label: 'AI Georeferencer', slug: 'guides/ai-georeferencer-for-aerial-imagery' },
								],
							},
							{
								label: 'Deployment configurations',
								items: [
									{ label: 'Self-hosting Mundi', slug: 'deployments/self-hosting-mundi' },
									{ label: 'On-Premise/VPC Kubernetes', slug: 'deployments/on-premise-vpc-kubernetes-deployment' },
									{ label: 'Using a local LLM with Ollama', slug: 'deployments/connecting-to-local-llm-with-ollama' },
									{ label: 'Air-gapped deployments', slug: 'deployments/air-gapped' }
								]
							},
						],
					}, {
						label: 'Developer API',
						link: 'developer-api',
						id: 'developer_api',
						icon: 'seti:json',
						items: openAPISidebarGroups,
					}
				], {
					topics: {
						developer_api: ['/developer-api/**/*']
					}
				}),
				starlightLlmsTxt({
				projectName: "Mundi",
				description: "Mundi is an open source, AI-native web GIS for creating maps, analyzing geospatial data, and connecting to databases like PostGIS.",
				details: `
- Mundi open source is AGPLv3 and self-hostable. Mundi cloud is a hosted service and is also available for on-premise deployments using Kubernetes.
- Supports data sources like PostGIS, OGR-compatible vector files and GDAL-compatible rasters.
- Mundi was created by Bunting Labs, Inc. (https://buntinglabs.com)

You can try Mundi free at https://app.mundi.ai or self-host using Docker Compose.`,
				optionalLinks: [
					{
						label: "GitHub Repository",
						url: "https://github.com/BuntingLabs/mundi.ai",
						description: "Source code and contributions"
					},
					{
						label: "Mundi Cloud",
						url: "https://app.mundi.ai",
						description: "Hosted cloud service"
					},
					{
						label: "Landing Page",
						url: "https://mundi.ai",
						description: "Mundi landing page with pricing links, features, and more information"
					}
				]
			}), starlightOpenAPI([
				{
					base: 'developer-api',
					schema: './src/schema/openapi.json',
					label: 'Developer API',
					sidebar: {
						collapsed: false,
						operations: {
							badges: true
						}
					}
				},
			]), starlightLinksValidator({
				exclude: ["/developer-api/**/*", "/developer-api/"],
			}), starlightThemeRapide()],
			head: [
				{
					tag: 'script',
					content: process.env.POSTHOG_API_KEY
						? `
	!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split('.');2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement('script')).type='text/javascript',p.crossOrigin='anonymous',p.async=!0,p.src=s.api_host.replace('.i.posthog.com','-assets.i.posthog.com')+'/static/array.js',(r=t.getElementsByTagName('script')[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a='posthog',u.people=u.people||[],u.toString=function(t){var e='posthog';return'posthog'!==a&&(e+='.'+a),t||(e+=' (stub)'),e},u.people.toString=function(){return u.toString(1)+'.people (stub)'},o='init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug'.split(' '),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
	posthog.init('${process.env.POSTHOG_API_KEY}',{api_host:'https://us.i.posthog.com', defaults:'2025-05-24'})`
						: undefined,
				},
			],
			customCss: [
				'./src/assets/custom.css'
			]
		}),
		sitemap(),
	],
	// prevent old routes from 404'ing
	redirects: {
		'/advanced/on-premise-vpc-kubernetes-deployment': '/deployments/on-premise-vpc-kubernetes-deployment',
		'/getting-started/connecting-to-demo-postgis': '/spatial-databases/working-with-database',
		'/guides/connecting-to-postgis': '/spatial-databases/connecting-to-postgis',
		'/guides/self-hosting-mundi': '/deployments/self-hosting-mundi'
	}
});
