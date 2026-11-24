# Phase 5B Analytics Dashboard Design

## Goal and scope

Add a responsive React analytics workspace at `/analytics` that consumes the existing Phase 5A APIs. Keep the work in the frontend and documentation. Do not change backend endpoints, models, migrations, or any Phase 6 behavior.

## Design

Use one dedicated workspace with source selectors for original and processed datasets and in-page sections for overview, column analytics, time series, correlation, aggregation, insights, and comparison. One selection model keeps the dashboard context consistent while avoiding duplicate pages. Source lists come from the existing datasets APIs; all analytics values and comparison results come from Phase 5A APIs.

Add typed request/response contracts and endpoint helpers to `services/api.ts`. Build the page from small presentational sections and page state, using the installed Recharts and existing dark theme tokens. Only request column detail, time series, aggregation, and comparisons when the corresponding user selection/action requires it. Render loading, empty, and recoverable API error states. Comparison candidates are original/processed pairs from the same lineage or processed outputs from the same original source.

## Verification

Add API service tests for endpoint paths, methods, and bodies, and page tests for source selection, type-specific analytics, controls, insights, comparisons, empty/loading/error states. Run the full frontend test suite and production build.
