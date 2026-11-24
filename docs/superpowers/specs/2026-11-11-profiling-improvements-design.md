# Profiling Improvements Design

## Intent

Improve Phase 2 reports for messy uploaded CSV/JSON values while preserving existing endpoints, persisted JSON reports, and the DataPulse detail-page design.

## Approach

Extend the current Pandas profiler rather than replacing ingestion or adding dependencies. Add explicit type inference, strict per-value numeric/date parsers, and type-specific JSON statistics; retain existing top-level profile fields and old nested fields where practical. Add a compact numeric histogram to the report so the existing Recharts view can display actual numeric distributions. Update the current column details panel to select numeric, categorical, date, identifier, or mixed details by inferred type. No schema migration is required because `profile_data` is JSON.

## Decisions

- New type labels: `integer`, `float`, `numeric_mixed`, `string`, `categorical`, `boolean`, `date`, `datetime`, `identifier`, `mixed`, and existing `empty`.
- Numeric text accepts correctly grouped comma separators such as `1,499`; malformed groupings remain invalid. Numeric mixed classification is available when numeric and invalid non-missing values coexist.
- Date parsing uses strict supported shapes (ISO date, slash date, day-month-year, and ISO datetime); shape-matching but impossible dates are retained as invalid date values.
- Missing values stay separate from invalid values. Numeric and date conversion percentages use non-missing values as their denominator.
- Identifier duplicate count means non-missing occurrences beyond the first distinct value. Identifier samples are capped at five; identifier columns do not receive frequency charts.
- Existing report fields and API paths stay in place. Reports are recalculated on generation/refresh; stored reports are not migrated or rewritten automatically.

## Scope

Backend profiling logic/tests, frontend type contracts and column-specific rendering, README interpretation notes. No Phase 3 ETL work, new database tables, migrations, or dependencies.
