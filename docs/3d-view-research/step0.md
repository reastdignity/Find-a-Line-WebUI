# Step 0: knock-out table (coordinator, 2026-11-01; quotes read on the pages by web-fetch agents)

## Google Map Tiles API, EEA — OUT
- "Photorealistic 3D tiles are not available." / "Satellite image tiles in 2D Tiles are not available." | https://developers.google.com/maps/comms/eea/map-tiles | updated 2026-10-30 | VERIFIED
- Scope: "(a) projects created after 8 July 2025 that are linked to an account with an EEA billing address" | same | VERIFIED
- "The Map Tiles API will throw a 403 HTTP error when you request these types of tiles from EEA projects." | same | VERIFIED
- Alternative: "3D Maps may be a suitable alternative in place of Photorealistic 3D Tiles." | same | VERIFIED
- Street View tiles: "No Use With any Map." | same | VERIFIED

## Google 3D Maps in Maps JavaScript API — PASSES provisionally
- EEA FAQ: "At this time, only the Services listed above are changing." (list: Maps Static, Map Tiles, Solar, Street View Static, Routes, Places, Geocoding, Address Validation; not Maps JavaScript API / 3D Maps) | https://developers.google.com/maps/comms/eea/faq | updated 2026-10-30 | VERIFIED
- New project with EEA billing → "your project will be subject to the EEA-specific Google Maps Platform ToS" | same | VERIFIED
- EEA ToS "removes three provisions from the "Restrictions Against Misusing the Services" section", incl. "No Use with Non-Google Maps" | same | VERIFIED
- EEA ToS adds "(b) responsibility for data misalignment and distinguishing Google content from non-Google content." | same | VERIFIED
- Pricing: SKU "Immersive Maps" (Pro), billable event "Map load", Free Usage Cap 5,000, then $7.00 per 1,000 (to 100k) | https://developers.google.com/maps/billing-and-pricing/pricing ; https://developers.google.com/maps/billing-and-pricing/sku-details/maps | updated 2026-10-30 | VERIFIED
- Dynamic Maps (10,000 free) trigger "With or without a map ID using Maps JavaScript API": not stated whether a 3D load also bills it | same | open
- CSP: "Maps JavaScript API supports the use of nonce-based strict CSP." "Websites must populate both script and style elements with a nonce value." | https://developers.google.com/maps/documentation/javascript/content-security-policy | VERIFIED
- Launch stage: releases "[beta channel] 3D Maps is now available in the beta channel." (2025-04-24); "3D Maps is now available in the weekly channel." (2025-10-23); 2026-10 entries add beta-tagged 3D properties | https://developers.google.com/maps/documentation/javascript/releases | VERIFIED
- Versioning: "Beta and alpha channels are solely for testing and development, containing features not ready for production use." | https://developers.google.com/maps/documentation/javascript/versions | VERIFIED
- Launch stages: "Preview offerings are intended for use in test environments only." | https://developers.google.com/maps/launch-stages | VERIFIED
- EEA ToS and EEA Service Specific Terms pages returned titles only to WebFetch (cloud.google.com/terms/maps-platform/eea, .../eea/maps-service-terms) → R1/R4 read raw.

## Cesium ion (Community) — OUT
- Pricing: "Personal and non-commercial use"; "Individual account only"; Google Photorealistic 3D Tiles "1,000 root tiles / month"; Global Imagery "1,000 sessions / month"; Streaming "15 GB / month"; Commercial "$149/month (individual)" | https://cesium.com/platform/cesium-ion/pricing/ | VERIFIED
- ToS 2.2.1: the Licensed Services "must be inaccessible to third parties" and "may not be operated ... as, or to perform, a service for or on behalf of any third parties." | https://cesium.com/legal/terms-of-service/ (major update 2025-08-20) | VERIFIED
- Pricing footnote: "Contact us if you plan to integrate Cesium ion into solutions used outside your organization." | pricing | VERIFIED
- Over quota: "Once over quota, your account will continue to work without interruption." | https://cesium.com/learn/ion/optimizing-quotas/ | VERIFIED
- ToS 4.1: "Should You exceed any usage limits in Your Plan, Cesium may invoice, and You shall pay, additional Fees." | ToS | VERIFIED → no hard stop
- ToS 2.2.3: "the 'Cesium ion' logo must be prominently displayed on the main application window of Your Application." | ToS | VERIFIED
- App B-2 (Google via ion): "You will not cache Google Maps Content except as expressly permitted..."; "You will not provide to Google ... any European End User's Personal Data" | https://cesium.com/legal/terms-for-google/ | VERIFIED

## Esri ArcGIS Location Platform — PASSES provisionally
- Basemap tiles "2M free then $0.15 per 1,000 tiles"; meter "the number of tile requests to basemaps-api.arcgis.com, ibasemaps-api.arcgis.com, or static-map-tiles-api.arcgis.com" | https://location.arcgis.com/pricing/ | VERIFIED
- Basemap sessions "1K free then $4 per 1,000 sessions" | same | VERIFIED
- Elevation values "50K free then $1 per 1,000 points" (at-point / at-many-points) | same | VERIFIED
- PAYG off: "your account will no longer have privileges to services that do not include a free tier or services in which you have exceeded the free tier." | https://location.arcgis.com/help/billing/ | VERIFIED → hard stop
- "Free tiers refresh at the start of your billing cycle." | same | VERIFIED
- "Usage is not recorded for any basemap tiles that may be cached in your users' web browser." | same | VERIFIED
- Scene ground "world-elevation" metering: not stated | https://developers.arcgis.com/documentation/mapping-and-location-services/mapping/scenes-3d/ | open (R2)

## MapTiler Cloud Free — passes formally, weak fidelity (one line)
- "Usage of the Free Plan is limited to non-commercial use and research & development for commercial products applications." (Cloud Terms 1.2); "commercial" undefined | https://www.maptiler.com/cloud/terms/ | VERIFIED
- "Sessions 5k/month"; "On a FREE plan service will pause until the next month without an upgrade to paid plans." ; "No credit card needed" | https://www.maptiler.com/cloud/pricing/ | VERIFIED
- Terrain "resolution 30x30 meters" (5 m "for selected countries in Europe") | https://www.maptiler.com/terrain/ | VERIFIED
- Server-side cache prohibited (Cloud Terms 7.2); free plan logo required (General Terms 6.1) | terms | VERIFIED

## Mapbox — OUT; Bing — OUT (peer audit 2026-11-01)
- Mapbox: "Mapbox does not provide the ability to cap your monthly billing" | peer audit (verified there) 
- Bing Maps free (Basic) accounts ended 2025-06-30 | peer audit
