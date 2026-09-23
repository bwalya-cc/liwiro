from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import csv
import io
import json
import math
import re

from .models import VerseAnalysisFinding, VerseAnalysisResult, VerseChartSpec


_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _slug_label(value: str) -> str:
    text = str(value or "").strip()
    return text or "Untitled dataset"


def _coerce_bool(value: str) -> bool | None:
    lowered = str(value or "").strip().lower()
    if lowered in {"true", "yes", "y", "1"}:
        return True
    if lowered in {"false", "no", "n", "0"}:
        return False
    return None


def _coerce_datetime(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidates = [raw]
    if raw.endswith("Z"):
        candidates.append(raw[:-1] + "+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.isoformat()
        except Exception:
            continue
    return None


def _coerce_numeric(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    raw = str(value or "").strip().replace(",", "")
    if not raw or not _NUMBER_RE.match(raw):
        return None
    try:
        number = float(raw)
    except Exception:
        return None
    if number.is_integer():
        return int(number)
    return number


def _sanitize_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True)
    raw = str(value).strip()
    if not raw:
        return None
    boolean_value = _coerce_bool(raw)
    if boolean_value is not None:
        return boolean_value
    number = _coerce_numeric(raw)
    if number is not None:
        return number
    timestamp = _coerce_datetime(raw)
    if timestamp is not None:
        return timestamp
    return raw


def _is_missing(value: Any) -> bool:
    """Avoid set membership: live records may legitimately contain objects."""
    return value is None or value == ""


def _normalize_rows(rows: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            item = {
                str(key).strip() or f"column_{position + 1}": _sanitize_cell(value)
                for position, (key, value) in enumerate(row.items())
            }
            normalized.append(item)
            continue
        if isinstance(row, list):
            normalized.append({f"column_{position + 1}": _sanitize_cell(value) for position, value in enumerate(row)})
            continue
        normalized.append({"value": _sanitize_cell(row), "row_index": index + 1})
    return [row for row in normalized if row]


def _rows_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _normalize_rows(payload)
    if isinstance(payload, dict):
        for key in ("rows", "data", "items", "records"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return _normalize_rows(nested)
        return _normalize_rows([payload])
    return []


def _sniff_delimiter(text: str, filename: str = "") -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix == ".tsv":
        return "\t"
    sample = str(text or "")[:2048]
    if "\t" in sample and sample.count("\t") >= sample.count(","):
        return "\t"
    return ","


def _rows_from_delimited_text(text: str, delimiter: str) -> list[dict[str, Any]]:
    stream = io.StringIO(str(text or ""))
    reader = csv.DictReader(stream, delimiter=delimiter)
    if not reader.fieldnames:
        stream.seek(0)
        plain_reader = csv.reader(stream, delimiter=delimiter)
        rows = list(plain_reader)
        if not rows:
            return []
        headers = [f"column_{index + 1}" for index in range(len(rows[0]))]
        return _normalize_rows([dict(zip(headers, row)) for row in rows])
    return _normalize_rows(list(reader))


def parse_dataset_text(raw_text: str, *, filename: str = "", format_hint: str = "") -> tuple[list[dict[str, Any]], str]:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("Dataset input is empty")
    normalized_hint = str(format_hint or "").strip().lower()
    suffix = Path(str(filename or "")).suffix.lower()
    if normalized_hint == "json" or suffix == ".json" or text.startswith("[") or text.startswith("{"):
        try:
            payload = json.loads(text)
        except Exception as exc:
            if normalized_hint == "json" or suffix == ".json":
                raise ValueError("Failed to parse JSON dataset") from exc
        else:
            rows = _rows_from_json(payload)
            if rows:
                return rows, "json"
    delimiter = "\t" if normalized_hint == "tsv" else _sniff_delimiter(text, filename=filename)
    rows = _rows_from_delimited_text(text, delimiter)
    if not rows:
        raise ValueError("No rows were parsed from the dataset input")
    return rows, "tsv" if delimiter == "\t" else "csv"


def infer_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys: list[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                keys.append(key)
    columns: list[dict[str, Any]] = []
    for key in keys:
        values = [row.get(key) for row in rows]
        non_null = [value for value in values if not _is_missing(value)]
        numeric_values = [float(value) for value in non_null if isinstance(value, (int, float))]
        bool_values = [value for value in non_null if isinstance(value, bool)]
        datetime_values = [value for value in non_null if isinstance(value, str) and _coerce_datetime(value)]
        column_type = "string"
        if non_null and len(numeric_values) == len(non_null):
            column_type = "number"
        elif non_null and len(bool_values) == len(non_null):
            column_type = "boolean"
        elif non_null and len(datetime_values) == len(non_null):
            column_type = "datetime"
        distinct = []
        distinct_seen = set()
        for value in non_null:
            text = str(value)
            if text in distinct_seen:
                continue
            distinct_seen.add(text)
            distinct.append(value)
            if len(distinct) >= 6:
                break
        columns.append(
            {
                "key": key,
                "label": key.replace("_", " ").replace("-", " ").title(),
                "type": column_type,
                "distinctCount": len({str(value) for value in non_null}),
                "nonNullCount": len(non_null),
                "sampleValues": distinct,
            }
        )
    return columns


def summarize_dataset(rows: list[dict[str, Any]], columns: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_columns = [column["key"] for column in columns if column.get("type") == "number"]
    categorical_columns = [column["key"] for column in columns if column.get("type") in {"string", "boolean"}]
    datetime_columns = [column["key"] for column in columns if column.get("type") == "datetime"]
    missing_cells = 0
    total_cells = max(len(rows) * max(len(columns), 1), 1)
    for row in rows:
        for column in columns:
            if _is_missing(row.get(str(column.get("key") or ""))):
                missing_cells += 1
    row_fingerprints = [json.dumps(row, sort_keys=True, default=str, separators=(",", ":")) for row in rows]
    duplicate_rows = max(0, len(row_fingerprints) - len(set(row_fingerprints)))
    column_quality = []
    for column in columns:
        key = str(column.get("key") or "")
        missing_count = sum(1 for row in rows if _is_missing(row.get(key)))
        column_quality.append({
            "key": key,
            "type": str(column.get("type") or "string"),
            "missingCount": missing_count,
            "missingRate": round(missing_count / max(len(rows), 1), 4),
            "distinctCount": int(column.get("distinctCount") or 0),
        })
    column_quality.sort(key=lambda item: (-item["missingRate"], item["key"]))
    metrics = {
        "rows": len(rows),
        "columns": len(columns),
        "numericColumns": len(numeric_columns),
        "categoricalColumns": len(categorical_columns),
        "datetimeColumns": len(datetime_columns),
        "missingCells": missing_cells,
        "missingRate": round(missing_cells / total_cells, 4),
        "duplicateRows": duplicate_rows,
        "duplicateRate": round(duplicate_rows / max(len(rows), 1), 4),
        "completeRows": sum(
            1 for row in rows
            if all(not _is_missing(row.get(str(column.get("key") or ""))) for column in columns)
        ),
    }
    return {
        "metrics": metrics,
        "numericColumns": numeric_columns,
        "categoricalColumns": categorical_columns,
        "datetimeColumns": datetime_columns,
        "hasTimeSeries": bool(datetime_columns and numeric_columns),
        "quality": {
            "columnQuality": column_quality,
            "duplicateRows": duplicate_rows,
            "duplicateRate": round(duplicate_rows / max(len(rows), 1), 4),
        },
    }


def serialize_dataset_preview(dataset: dict[str, Any], *, limit: int = 12) -> dict[str, Any]:
    rows = list(dataset.get("rows") or [])
    columns = list(dataset.get("columns") or [])
    source = dict(dataset.get("source") or {})
    return {
        "id": str(dataset.get("dataset_id") or dataset.get("id") or ""),
        "title": str(dataset.get("title") or "Dataset"),
        "ownerUsername": str(dataset.get("owner_username") or dataset.get("ownerUsername") or ""),
        "createdAt": str(dataset.get("created_at") or dataset.get("createdAt") or ""),
        "updatedAt": str(dataset.get("updated_at") or dataset.get("updatedAt") or ""),
        "source": {
            "sourceType": str(source.get("source_type") or source.get("sourceType") or ""),
            "format": str(source.get("format") or ""),
            "filename": str(source.get("filename") or ""),
            "archivedName": str(source.get("archived_name") or source.get("archivedName") or ""),
            "archivedPath": str(source.get("archived_path") or source.get("archivedPath") or ""),
            "pageKind": str(source.get("page_kind") or source.get("pageKind") or ""),
        },
        "rowCount": len(rows),
        "columnCount": len(columns),
        "columns": columns,
        "summary": dict(dataset.get("summary") or {}),
        "previewRows": rows[: max(1, int(limit))],
        "notes": str(dataset.get("notes") or ""),
    }


def _column_lookup(columns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(column.get("key") or ""): column for column in columns if str(column.get("key") or "").strip()}


def _numeric_columns(columns: list[dict[str, Any]]) -> list[str]:
    return [str(column.get("key") or "") for column in columns if column.get("type") == "number"]


def _dimension_candidates(columns: list[dict[str, Any]]) -> list[str]:
    preferred = []
    for column in columns:
        key = str(column.get("key") or "")
        column_type = str(column.get("type") or "")
        if column_type in {"datetime", "string", "boolean"}:
            preferred.append(key)
    if preferred:
        return preferred
    return [str(column.get("key") or "") for column in columns]


def _default_chart_type(columns: list[dict[str, Any]]) -> str:
    numeric_columns = _numeric_columns(columns)
    datetime_columns = [column for column in columns if column.get("type") == "datetime"]
    categorical_columns = [column for column in columns if column.get("type") in {"string", "boolean"}]
    if datetime_columns and numeric_columns:
        return "line"
    if len(numeric_columns) >= 2:
        return "scatter"
    if categorical_columns and numeric_columns:
        return "bar"
    if categorical_columns:
        return "leaderboard"
    if numeric_columns:
        return "metric-list"
    return "table"


def available_chart_types(columns: list[dict[str, Any]]) -> list[str]:
    chart_types = ["table", "metric-list"]
    numeric_columns = _numeric_columns(columns)
    dimension_columns = _dimension_candidates(columns)
    if numeric_columns and dimension_columns:
        chart_types.extend(["bar", "grouped-bar", "stacked-bar", "pie", "donut"])
        if any(column.get("type") == "datetime" for column in columns):
            chart_types.extend(["line", "area", "anomaly-timeline"])
    if len(numeric_columns) >= 2:
        chart_types.append("scatter")
    if numeric_columns:
        chart_types.append("histogram")
    if dimension_columns:
        chart_types.append("leaderboard")
    deduped = []
    for item in chart_types:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _apply_filters(rows: list[dict[str, Any]], filters: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not filters:
        return rows
    filtered = list(rows)
    for item in filters:
        if not isinstance(item, dict):
            continue
        key = str(item.get("column") or item.get("key") or "").strip()
        op = str(item.get("op") or "eq").strip().lower()
        raw_value = item.get("value")
        if not key:
            continue
        if op == "contains":
            # Do not use ``value or ""`` here: false and zero are legitimate
            # values in platform datasets and must remain filterable.
            needle = "" if raw_value is None else str(raw_value).strip().lower()
            if needle == "":
                continue
            filtered = [row for row in filtered if needle in str(row.get(key, "")).lower()]
        elif op == "gte":
            threshold = _coerce_numeric(raw_value)
            if threshold is None:
                continue
            filtered = [
                row for row in filtered
                if not isinstance(row.get(key), bool)
                and _coerce_numeric(row.get(key)) is not None
                and float(_coerce_numeric(row.get(key))) >= float(threshold)
            ]
        elif op == "lte":
            threshold = _coerce_numeric(raw_value)
            if threshold is None:
                continue
            filtered = [
                row for row in filtered
                if not isinstance(row.get(key), bool)
                and _coerce_numeric(row.get(key)) is not None
                and float(_coerce_numeric(row.get(key))) <= float(threshold)
            ]
        else:
            expected_bool = _coerce_bool(raw_value)
            if expected_bool is not None:
                filtered = [row for row in filtered if row.get(key) is expected_bool]
            else:
                expected = "" if raw_value is None else str(raw_value)
                filtered = [row for row in filtered if str(row.get(key, "")) == expected]
    return filtered


def _aggregate_value(values: list[float], aggregation: str) -> float:
    if aggregation == "avg":
        return sum(values) / len(values) if values else 0.0
    if aggregation == "min":
        return min(values) if values else 0.0
    if aggregation == "max":
        return max(values) if values else 0.0
    if aggregation == "count":
        return float(len(values))
    return sum(values)


def _group_rows(
    rows: list[dict[str, Any]],
    *,
    dimension: str,
    metric: str,
    aggregation: str,
    compare_by: str = "",
    limit: int = 12,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        dimension_value = str(row.get(dimension) or "Unknown")
        compare_value = str(row.get(compare_by) or "Series") if compare_by else ""
        if aggregation == "count" or not metric:
            grouped[dimension_value][compare_value].append(1.0)
            continue
        metric_value = row.get(metric)
        if isinstance(metric_value, (int, float)):
            grouped[dimension_value][compare_value].append(float(metric_value))
    output = []
    for dimension_value, compare_map in grouped.items():
        item = {"label": dimension_value}
        total = 0.0
        for compare_value, values in compare_map.items():
            key = compare_value or metric or "value"
            aggregated = _aggregate_value(values, aggregation)
            item[key] = round(aggregated, 4)
            total += aggregated
        item["total"] = round(total, 4)
        output.append(item)
    output.sort(key=lambda item: float(item.get("total") or 0), reverse=True)
    return output[: max(1, int(limit))]


def _histogram_data(rows: list[dict[str, Any]], metric: str, limit: int = 10) -> list[dict[str, Any]]:
    values = [float(row.get(metric)) for row in rows if isinstance(row.get(metric), (int, float))]
    if not values:
        return []
    lower = min(values)
    upper = max(values)
    if lower == upper:
        return [{"label": str(lower), "count": len(values)}]
    bucket_count = max(4, min(int(limit), 12))
    step = (upper - lower) / bucket_count
    buckets = []
    for index in range(bucket_count):
        start = lower + step * index
        end = upper if index == bucket_count - 1 else start + step
        if index == bucket_count - 1:
            count = len([value for value in values if value >= start and value <= end])
        else:
            count = len([value for value in values if value >= start and value < end])
        label = f"{round(start, 2)}-{round(end, 2)}"
        buckets.append({"label": label, "count": count})
    return buckets


def _metric_cards(rows: list[dict[str, Any]], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = [
        {"label": "Rows", "value": len(rows), "accent": "slate"},
        {"label": "Columns", "value": len(columns), "accent": "slate"},
    ]
    numeric_columns = _numeric_columns(columns)[:4]
    for key in numeric_columns:
        values = [float(row.get(key)) for row in rows if isinstance(row.get(key), (int, float))]
        if not values:
            continue
        metrics.append({"label": f"{key} avg", "value": round(sum(values) / len(values), 3), "accent": "teal"})
    return metrics[:6]


def _analysis_preset_options(columns: list[dict[str, Any]]) -> list[dict[str, str]]:
    numeric_columns = _numeric_columns(columns)
    has_datetime = any(column.get("type") == "datetime" for column in columns)
    has_categorical = any(column.get("type") in {"string", "boolean"} for column in columns)
    presets = []
    if has_datetime and numeric_columns:
        presets.append(
            {
                "id": "trend-over-time",
                "label": "Trend over time",
                "chartType": "line",
                "intent": "trend",
            }
        )
        presets.append(
            {
                "id": "find-anomalies",
                "label": "Find anomalies",
                "chartType": "anomaly-timeline",
                "intent": "anomaly",
            }
        )
    if has_categorical and numeric_columns:
        presets.append(
            {
                "id": "compare-groups",
                "label": "Compare groups",
                "chartType": "grouped-bar",
                "intent": "comparison",
            }
        )
        presets.append(
            {
                "id": "explain-drivers",
                "label": "Explain drivers",
                "chartType": "leaderboard",
                "intent": "drivers",
            }
        )
    if numeric_columns:
        presets.append(
            {
                "id": "show-distribution",
                "label": "Show distribution",
                "chartType": "histogram",
                "intent": "distribution",
            }
        )
    return presets


def _detect_patterns(rows: list[dict[str, Any]], columns: list[dict[str, Any]], dimension: str, metric: str) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    if metric:
        values = [float(row.get(metric)) for row in rows if isinstance(row.get(metric), (int, float))]
        if values:
            average = sum(values) / len(values)
            spread = max(values) - min(values)
            if spread > 0:
                patterns.append({"type": "range", "label": metric, "value": round(spread, 3)})
            if average:
                patterns.append({"type": "average", "label": metric, "value": round(average, 3)})
    if dimension:
        counts = Counter(str(row.get(dimension) or "Unknown") for row in rows)
        if counts:
            label, value = counts.most_common(1)[0]
            patterns.append({"type": "dominant-segment", "label": label, "value": value})
    return patterns[:4]


def _uncertainty_notes(rows: list[dict[str, Any]], columns: list[dict[str, Any]], metric: str, dimension: str) -> list[str]:
    notes: list[str] = []
    summary = summarize_dataset(rows, columns)
    missing_rate = float(((summary.get("metrics") or {}).get("missingRate") or 0.0))
    if missing_rate >= 0.15:
        notes.append("Some columns have meaningful missing data, so trend and segment conclusions may be incomplete.")
    duplicate_rate = float(((summary.get("metrics") or {}).get("duplicateRate") or 0.0))
    if duplicate_rate > 0:
        notes.append("Duplicate rows were detected; totals and counts may be inflated until those records are reviewed.")
    if metric:
        numeric_values = [row.get(metric) for row in rows if isinstance(row.get(metric), (int, float))]
        if len(numeric_values) < 3:
            notes.append("There are only a few numeric observations for the selected metric, so outlier detection is limited.")
    if dimension and len({str(row.get(dimension) or "Unknown") for row in rows}) <= 1:
        notes.append("The selected dimension has very low variation, so comparisons may not be very informative.")
    return notes[:3]


def _analysis_intent(chart_type: str, dimension: str, compare_by: str) -> str:
    normalized = str(chart_type or "").strip().lower()
    if normalized in {"line", "area", "anomaly-timeline"}:
        return "trend"
    if normalized in {"scatter"}:
        return "correlation"
    if normalized in {"histogram"}:
        return "distribution"
    if normalized in {"pie", "donut"}:
        return "composition"
    if normalized in {"grouped-bar", "stacked-bar", "leaderboard"}:
        return "comparison" if compare_by or dimension else "ranking"
    if normalized == "metric-list":
        return "summary"
    if normalized == "table":
        return "inspection"
    return "comparison"


def _confidence_for_analysis(rows: list[dict[str, Any]], chart_data: list[dict[str, Any]], uncertainty_notes: list[str]) -> str:
    if not rows or not chart_data:
        return "Low"
    if len(chart_data) >= 4 and not uncertainty_notes:
        return "High"
    if len(chart_data) >= 2:
        return "Medium"
    return "Low"


def _anomaly_points(rows: list[dict[str, Any]], x_key: str, metric: str) -> list[dict[str, Any]]:
    numeric_values = [float(row.get(metric)) for row in rows if isinstance(row.get(metric), (int, float))]
    if len(numeric_values) < 4:
        return []
    average = sum(numeric_values) / len(numeric_values)
    variance = sum((value - average) ** 2 for value in numeric_values) / len(numeric_values)
    deviation = math.sqrt(variance)
    if deviation == 0:
        return []
    outliers = []
    for row in rows:
        value = row.get(metric)
        if not isinstance(value, (int, float)):
            continue
        if abs(float(value) - average) >= deviation * 1.5:
            outliers.append({"x": row.get(x_key), "y": value, "label": str(row.get(x_key) or "Observation")})
    return outliers[:8]


def _normalize_chart_payload(
    chart: dict[str, Any],
    *,
    fallback_title: str,
    fallback_description: str,
    table_preview: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = dict(chart or {})
    chart_type = str(normalized.get("chartType") or "metric-list").strip().lower()
    data = [dict(item) for item in list(normalized.get("data") or []) if isinstance(item, dict)]
    x_key = str(normalized.get("xKey") or "").strip()
    y_keys = [str(item).strip() for item in list(normalized.get("yKeys") or []) if str(item).strip()]
    value_key = str(normalized.get("valueKey") or "").strip()
    table_columns = [str(item).strip() for item in list(normalized.get("tableColumns") or []) if str(item).strip()]
    fallback_reason = ""
    status = "ready"
    supported_types = {"bar", "grouped-bar", "stacked-bar", "line", "area", "pie", "donut", "scatter", "table", "metric-list", "leaderboard", "histogram", "anomaly-timeline"}
    if chart_type not in supported_types:
        chart_type = "table" if table_preview else "metric-list"
        fallback_reason = "Unsupported chart type was replaced with a safe fallback."
        status = "fallback"
    if chart_type in {"line", "area", "anomaly-timeline"} and (not data or not x_key or not y_keys):
        chart_type = "table" if table_preview else "metric-list"
        fallback_reason = "Trend view did not have enough ordered axis data to render safely."
        status = "fallback"
    elif chart_type == "scatter" and (not data or not x_key or not y_keys):
        chart_type = "table" if table_preview else "metric-list"
        fallback_reason = "Scatter view requires numeric x and y keys."
        status = "fallback"
    elif chart_type in {"pie", "donut", "histogram", "bar", "grouped-bar", "stacked-bar", "leaderboard"} and not data:
        chart_type = "table" if table_preview else "metric-list"
        fallback_reason = "The selected chart had no renderable data."
        status = "fallback"
    elif chart_type == "metric-list" and not metrics:
        chart_type = "table" if table_preview else "metric-list"
        if chart_type == "table":
            fallback_reason = "Metric cards were unavailable, so the dataset preview is shown instead."
            status = "fallback"
    normalized["chartType"] = chart_type
    normalized["title"] = str(normalized.get("title") or fallback_title).strip() or fallback_title
    normalized["description"] = str(normalized.get("description") or fallback_description).strip()
    normalized["status"] = status
    normalized["fallbackReason"] = fallback_reason
    normalized["data"] = data[:80]
    normalized["xKey"] = x_key
    normalized["yKeys"] = y_keys
    normalized["valueKey"] = value_key
    normalized["tableColumns"] = table_columns
    return normalized


def _findings(rows: list[dict[str, Any]], columns: list[dict[str, Any]], dimension: str = "", metric: str = "") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not rows:
        return findings
    findings.append(
        VerseAnalysisFinding(
            title="Dataset coverage",
            description=f"Loaded {len(rows)} rows across {len(columns)} columns for review.",
            severity="info",
        ).to_dict()
    )
    summary = summarize_dataset(rows, columns)
    duplicate_rows = int((summary.get("metrics") or {}).get("duplicateRows") or 0)
    if duplicate_rows:
        findings.append(
            VerseAnalysisFinding(
                title="Duplicate records detected",
                description=f"{duplicate_rows} duplicate row(s) were found in the current dataset view.",
                severity="warning",
            ).to_dict()
        )
    if metric:
        values = [float(row.get(metric)) for row in rows if isinstance(row.get(metric), (int, float))]
        if values:
            findings.append(
                VerseAnalysisFinding(
                    title="Observed range",
                    description=f"{metric} ranges from {round(min(values), 3)} to {round(max(values), 3)}.",
                    severity="info",
                ).to_dict()
            )
    if dimension:
        counts = Counter(str(row.get(dimension) or "Unknown") for row in rows)
        if counts:
            label, count = counts.most_common(1)[0]
            findings.append(
                VerseAnalysisFinding(
                    title="Largest segment",
                    description=f"{label} appears most often in {dimension} with {count} row(s).",
                    severity="info",
                ).to_dict()
            )
    return findings[:4]


def build_analysis_view(dataset: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = dict(options or {})
    rows = list(dataset.get("rows") or [])
    columns = list(dataset.get("columns") or [])
    filtered_rows = _apply_filters(rows, options.get("filters") if isinstance(options.get("filters"), list) else [])
    requested_chart_type = str(options.get("chartType") or options.get("type") or "").strip().lower()
    chart_type = str(requested_chart_type or _default_chart_type(columns)).strip().lower()
    aggregation = str(options.get("aggregation") or "sum").strip().lower()
    limit = max(3, min(int(options.get("limit") or 12), 50))
    column_map = _column_lookup(columns)
    dimension_candidates = _dimension_candidates(columns)
    numeric_columns = _numeric_columns(columns)
    dimension = str(options.get("dimension") or options.get("xKey") or (dimension_candidates[0] if dimension_candidates else "")).strip()
    metric = str(options.get("metric") or options.get("valueKey") or (numeric_columns[0] if numeric_columns else "")).strip()
    compare_by = str(options.get("compareBy") or options.get("seriesKey") or "").strip()
    secondary_metric = str(options.get("secondaryMetric") or options.get("yKey") or (numeric_columns[1] if len(numeric_columns) > 1 else "")).strip()
    selected_preset = str(options.get("preset") or "").strip()
    available_types = available_chart_types(columns)
    requested_chart_unavailable = bool(requested_chart_type and requested_chart_type not in available_types)
    if chart_type not in available_types:
        chart_type = _default_chart_type(columns)

    chart: dict[str, Any]
    if chart_type in {"bar", "grouped-bar", "stacked-bar", "leaderboard", "pie", "donut"}:
        if not dimension and dimension_candidates:
            dimension = dimension_candidates[0]
        if not metric and aggregation != "count" and numeric_columns:
            metric = numeric_columns[0]
        grouped = _group_rows(
            filtered_rows,
            dimension=dimension or (dimension_candidates[0] if dimension_candidates else "label"),
            metric=metric,
            aggregation=aggregation,
            compare_by=compare_by if chart_type in {"grouped-bar", "stacked-bar"} else "",
            limit=limit,
        )
        series_keys = [key for key in grouped[0].keys() if key not in {"label", "total"}] if grouped else []
        value_key = series_keys[0] if series_keys else "total"
        chart = VerseChartSpec(
            chart_type=chart_type,
            title=_slug_label(options.get("title") or dataset.get("title") or "Analysis"),
            description=str(options.get("description") or "").strip(),
            intent=_analysis_intent(chart_type, dimension, compare_by),
            data=grouped,
            x_key="label",
            y_keys=series_keys or [value_key],
            value_key=value_key,
            series_key=compare_by if chart_type in {"grouped-bar", "stacked-bar"} else "",
            category_order=[str(item.get("label") or "") for item in grouped],
            stacked=chart_type == "stacked-bar",
            horizontal=chart_type == "leaderboard",
        ).to_dict()
    elif chart_type in {"line", "area", "anomaly-timeline"}:
        x_key = dimension if column_map.get(dimension, {}).get("type") == "datetime" else (next((col["key"] for col in columns if col.get("type") == "datetime"), dimension or "label"))
        y_keys = [metric] if metric else numeric_columns[:1]
        if compare_by and len(numeric_columns) > 1 and compare_by not in y_keys:
            y_keys = numeric_columns[: min(3, len(numeric_columns))]
        line_rows = []
        for row in filtered_rows[: max(limit, 24)]:
            item = {x_key: row.get(x_key)}
            for key in y_keys:
                item[key] = row.get(key)
            line_rows.append(item)
        chart = VerseChartSpec(
            chart_type="anomaly-timeline" if chart_type == "anomaly-timeline" else chart_type,
            title=_slug_label(options.get("title") or dataset.get("title") or "Trend"),
            description=str(options.get("description") or "").strip(),
            intent=_analysis_intent(chart_type, x_key, compare_by),
            status="fallback" if str(column_map.get(x_key, {}).get("type") or "") not in {"datetime", "number"} else "ready",
            fallback_reason="Trend views require an ordered x-axis, so this result fell back because the selected dimension is not time-like or numeric."
            if str(column_map.get(x_key, {}).get("type") or "") not in {"datetime", "number"}
            else "",
            data=line_rows,
            x_key=x_key,
            y_keys=y_keys,
            anomaly_points=_anomaly_points(line_rows, x_key, y_keys[0] if y_keys else ""),
        ).to_dict()
    elif chart_type == "scatter":
        x_key = metric or (numeric_columns[0] if numeric_columns else "")
        y_key = secondary_metric or (numeric_columns[1] if len(numeric_columns) > 1 else x_key)
        scatter_rows = []
        for row in filtered_rows[: max(limit * 4, 40)]:
            x_value = row.get(x_key)
            y_value = row.get(y_key)
            if isinstance(x_value, (int, float)) and isinstance(y_value, (int, float)):
                item = {x_key: x_value, y_key: y_value}
                if compare_by:
                    item[compare_by] = row.get(compare_by)
                scatter_rows.append(item)
        chart = VerseChartSpec(
            chart_type="scatter",
            title=_slug_label(options.get("title") or dataset.get("title") or "Scatter plot"),
            description=str(options.get("description") or "").strip(),
            intent=_analysis_intent("scatter", x_key, compare_by),
            data=scatter_rows,
            x_key=x_key,
            y_keys=[y_key],
            series_key=compare_by,
        ).to_dict()
    elif chart_type == "histogram":
        target_metric = metric or (numeric_columns[0] if numeric_columns else "")
        histogram_rows = _histogram_data(filtered_rows, target_metric, limit=limit)
        chart = VerseChartSpec(
            chart_type="histogram",
            title=_slug_label(options.get("title") or dataset.get("title") or "Distribution"),
            description=str(options.get("description") or "").strip(),
            intent=_analysis_intent("histogram", "", ""),
            data=histogram_rows,
            x_key="label",
            y_keys=["count"],
            value_key="count",
            bins=list(histogram_rows),
        ).to_dict()
    elif chart_type == "table":
        preview = filtered_rows[:limit]
        chart = VerseChartSpec(
            chart_type="table",
            title=_slug_label(options.get("title") or dataset.get("title") or "Table view"),
            description=str(options.get("description") or "").strip(),
            intent=_analysis_intent("table", dimension, compare_by),
            data=preview,
            table_columns=[str(column.get("key") or "") for column in columns],
        ).to_dict()
    else:
        chart = VerseChartSpec(
            chart_type="metric-list",
            title=_slug_label(options.get("title") or dataset.get("title") or "Summary metrics"),
            description=str(options.get("description") or "").strip(),
            intent=_analysis_intent("metric-list", dimension, compare_by),
            data=[],
        ).to_dict()

    preview = filtered_rows[: min(limit, 20)]
    insight_notes = []
    dataset_summary = summarize_dataset(filtered_rows, columns)
    if (dataset_summary.get("metrics") or {}).get("rows"):
        insight_notes.append(
            f"The dataset currently exposes {dataset_summary['metrics']['rows']} rows across {dataset_summary['metrics']['columns']} columns."
        )
    if dataset_summary.get("hasTimeSeries"):
        insight_notes.append("A time dimension was detected, so trend and anomaly views are available.")
    if compare_by:
        insight_notes.append(f"Comparisons are split by {compare_by}.")
    presets = _analysis_preset_options(columns)
    uncertainty_notes = _uncertainty_notes(filtered_rows, columns, metric, dimension)
    chart = _normalize_chart_payload(
        chart,
        fallback_title=str(chart.get("title") or dataset.get("title") or "Analysis"),
        fallback_description=str(chart.get("description") or ""),
        table_preview=preview,
        metrics=_metric_cards(filtered_rows, columns),
    )
    if requested_chart_unavailable:
        chart["status"] = "fallback"
        chart["chartType"] = "table" if preview else "metric-list"
        chart["fallbackReason"] = chart.get("fallbackReason") or "The requested chart type is not supported for the current dataset shape, so a safer view was used."
    detected_patterns = _detect_patterns(filtered_rows, columns, dimension, metric)
    confidence = _confidence_for_analysis(filtered_rows, list(chart.get("data") or []), uncertainty_notes)
    chart["confidence"] = confidence
    chart["intent"] = str(chart.get("intent") or _analysis_intent(str(chart.get("chartType") or ""), dimension, compare_by)).strip()
    result = VerseAnalysisResult(
        dataset_id=str(dataset.get("dataset_id") or dataset.get("id") or ""),
        title=str(chart.get("title") or "Analysis snapshot"),
        description=str(chart.get("description") or ""),
        chart=chart,
        intent=str(chart.get("intent") or ""),
        confidence=confidence,
        alternate_chart_types=[item for item in available_types if item != chart_type][:6],
        metrics=_metric_cards(filtered_rows, columns),
        findings=_findings(filtered_rows, columns, dimension=dimension, metric=metric),
        insight_notes=insight_notes[:4],
        detected_patterns=detected_patterns,
        uncertainty_notes=uncertainty_notes,
        table_preview=preview,
        controls={
            "chartTypes": available_types,
            "dimensions": dimension_candidates,
            "metrics": numeric_columns,
            "compareDimensions": [column["key"] for column in columns if column.get("type") in {"string", "boolean"} and column.get("key") != dimension],
            "aggregations": ["sum", "avg", "count", "min", "max"],
            "presets": presets,
            "selected": {
                "preset": selected_preset,
                "chartType": chart_type,
                "dimension": dimension,
                "metric": metric,
                "secondaryMetric": secondary_metric,
                "compareBy": compare_by,
                "aggregation": aggregation,
                "filters": options.get("filters") if isinstance(options.get("filters"), list) else [],
                "limit": limit,
            },
            "columns": columns,
        },
        dataset={**serialize_dataset_preview(dataset, limit=limit), "analysisSummary": dataset_summary},
    )
    return result.to_dict()
