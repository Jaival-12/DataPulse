# DataPulse Phase 3B Frontend Design

## Intent and scope

Integrate the existing Phase 3A pipeline and processed dataset APIs into the React application. Users can manage pipelines, configure ordered transformations with structured forms, execute synchronously, inspect history and logs, and preview/download processed results. Existing upload, dataset detail, and profile routes remain intact; no backend or migration changes are planned.

## Existing contracts

- Pipeline list/detail: `PipelinePage {items,total,limit,offset}` and `PipelineOut {id,name,description,source_dataset_id,configuration,steps}`. Step output uses `operation`, `configuration`, and `execution_order`.
- Pipeline create accepts `name`, optional `description`, `source_dataset_id`, `output_format`, and `steps: [{operation,config}]`. Update accepts those fields optionally.
- Execution: POST returns execution status/timestamps/duration/input and output rows/error, optional `processed_dataset`, and `execution_summary.logs`. Pipeline history is a paginated page. Execution detail and logs have separate endpoints.
- Processed dataset list/detail returns IDs for source and execution, file metadata, counts, path, and timestamp. Preview returns `{dataset, rows}`. Download returns a file response.
- Operation configs are validated from backend Pydantic contracts: remove duplicates (`subset?`); fill missing (`drop_rows`, `constant`, `mean`, `median`, `mode`); rename (`mapping`); remove/reorder/text standardization (`columns`); filter (`column`, `operator`, scalar `value` except null checks); convert (`column`, `target_type`); calculated (`name`, structured `left`/`right`, arithmetic operator).

## Architecture

Add typed client contracts and API calls to the existing API client. Add route-level pages for pipeline list, pipeline builder/detail, processed dataset list, and processed dataset detail. Keep transformation forms in a reusable step editor and use ordinary move-up/down controls. Use existing layout, shared dark palette, buttons, panels, and table styles; add focused responsive CSS for new screens.

The pipeline detail route supports create and edit, with Builder and Runs tabs. It fetches datasets for column choices, validates and normalizes configs before save, and updates available columns after rename/remove/calculated/reorder steps. Run requests show a synchronous waiting state only; on response, refresh pipeline/execution history and present the real result. Execution detail explicitly loads both detail and logs APIs.

Processed dataset detail fetches its source dataset and execution/pipeline metadata to display readable names, then previews records and downloads the returned file through a blob URL. The catalog resolves names for its current page only and remains paginated.

## Design calls

- No drag-and-drop library: numbered cards have accessible Move up/Move down controls.
- No mock execution progress: disable the run button and show a spinner/“Executing synchronously” label until the response arrives.
- Creation and editing share the same route component; route `/pipelines/new` creates and `/pipelines/{id}` edits/details.
- Processed dataset detail resolves related source and pipeline names through existing metadata endpoints because the processed response contains IDs only.
- Keep backend/API/migrations and existing Phase 1/2 pages unchanged unless verification reveals a real incompatibility.

## Validation and states

Show loading, empty, API error, field/config validation, saved, run success, run failure, and delete confirmation states. Keep invalid or incomplete step forms visible and block Save until required fields are complete. Never place arbitrary code input in calculated-column UI.

## Out of scope

Phase 4, scheduled/background execution, real-time progress, workflow graphs, authentication, and backend contract changes.
