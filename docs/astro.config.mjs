// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';
import sitemap from '@astrojs/sitemap';

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
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/BuntingLabs/mundi.ai' }],
			sidebar: [
				{
					label: 'Introduction',
					slug: 'index',
				},
				{
					label: 'Getting started',
					items: [
						{ label: 'Making your first map', slug: 'getting-started/making-your-first-map' },
						{ label: 'Connecting to a demo database', slug: 'getting-started/connecting-to-demo-postgis' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ label: 'Connecting to PostGIS', slug: 'guides/connecting-to-postgis' },
						{ label: 'Geoprocessing from QGIS', slug: 'guides/geoprocessing-from-qgis' },
						{ label: 'Satellite basemaps', slug: 'guides/switching-basemaps-satellite-or-traditional-vector' },
					],
				},
				{
					label: 'Deployment configurations',
					items: [
						{ label: 'Self-hosting Mundi', slug: 'deployments/self-hosting-mundi' },
						{ label: 'On-Premise/VPC Kubernetes', slug: 'deployments/on-premise-vpc-kubernetes-deployment' },
						{ label: 'Using a local LLM with Ollama', slug: 'deployments/connecting-to-local-llm-with-ollama' }
					]
				}
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
			plugins: [starlightLlmsTxt({
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
						label: "Live Demo",
						url: "https://app.mundi.ai",
						description: "Hosted cloud service"
					},
					{
						label: "Landing Page",
						url: "https://mundi.ai",
						description: "Mundi landing page with pricing links, features, and more information"
					}
				]
			})]
		}),
		sitemap(),
	],
	// prevent old routes from 404'ing
	redirects: {
		'/advanced/on-premise-vpc-kubernetes-deployment': '/deployments/on-premise-vpc-kubernetes-deployment',
		'/guides/self-hosting-mundi': '/deployments/self-hosting-mundi'
	}
});
