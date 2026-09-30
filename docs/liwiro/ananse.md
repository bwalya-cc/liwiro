# Ananse Workbench

Use **Ananse** (`/ananse-workbench`) to explore service health and platform activity. Its live datasets contain observations available to your account, including service status, request volume, errors, and response times.

## Explore a dataset

1. Open Ananse and select a dataset from the available sources.
2. Review its columns and row count before choosing a chart.
3. Apply text, equality, or numeric range filters to focus the analysis.
4. Choose dimensions, metrics, and a visualization suited to the question.
5. Inspect the table and data-quality findings alongside the chart.

Charts refresh every 30 seconds. Service traffic appears as requests arrive. Access follows your service permissions, so two users may see different data.

## Read the findings

Missing rate describes cells without usable values. Duplicate rows count exact repeated records, while complete rows contain no missing values. A time-series indicator tells you whether time-based analysis is available; it does not guarantee a meaningful trend.

Service Performance summarizes request counts, error rates, average latency, and approximate p95 latency. Treat short or sparse observation windows with care when comparing services. Confidence and uncertainty notes describe the analysis, rather than certifying that a service is healthy.

## Work with Verse

Ask Ananse in Verse Chat to interpret a dataset or review a pattern. Include the service, time window, and question you want answered. Review the source data and filters before acting on a recommendation.

## Troubleshooting

- **No sources:** check account permissions and whether platform observations are available.
- **No service traffic:** send requests to the service, then allow the next refresh.
- **Empty chart after filtering:** inspect the filters and selected columns.
- **Missing fields:** use a chart type supported by the available data, or inspect the table directly.
