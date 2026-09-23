#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[3]
REFERENCE_PATH = ROOT / "verun" / "vi" / "versa-wiki" / "versa-reference.json"
VVR_PATH = ROOT / "verun" / "vi" / "verse-verun-reference" / "reference.json"
EVALUATOR_PATH = ROOT / "verun" / "vi" / "src" / "main" / "java" / "verun" / "runtime" / "evaluator" / "Evaluator.java"
MEMBER_ACCESS_PATH = ROOT / "verun" / "vi" / "src" / "main" / "java" / "verun" / "runtime" / "evaluator" / "MemberAccessEvaluator.java"
STRING_EVAL_PATH = ROOT / "verun" / "vi" / "src" / "main" / "java" / "verun" / "runtime" / "evaluator" / "StringEvaluator.java"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ensure_expected(label: str, text: str, needles: list[str]) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise RuntimeError(f"{label} is missing expected runtime markers: {', '.join(missing)}")


def replace_or_append_section(sections: list[dict], section: dict) -> None:
    section_id = str(section.get("id") or "").strip()
    for index, existing in enumerate(sections):
        if str(existing.get("id") or "").strip() == section_id:
            sections[index] = section
            return
    sections.append(section)


def get_section(sections: list[dict], section_id: str) -> dict | None:
    for section in sections:
        if str(section.get("id") or "").strip() == section_id:
            return section
    return None


def unique_source_entries(entries: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for entry in entries:
        path = str(entry.get("path") or "").strip()
        purpose = str(entry.get("purpose") or "").strip()
        if not path:
            continue
        key = (path, purpose)
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": path, "purpose": purpose})
    return out


def build_method_section(
    *,
    section_id: str,
    title: str,
    summary: str,
    tags: list[str],
    constructs: list[str],
    query_hints: list[str],
    syntax_patterns: list[str],
    rules: list[str],
    tables: list[dict],
    valid_examples: list[dict],
) -> dict:
    return {
        "id": section_id,
        "title": title,
        "summary": summary,
        "tags": tags,
        "constructs": constructs,
        "queryHints": query_hints,
        "syntaxPatterns": syntax_patterns,
        "rules": rules,
        "tables": tables,
        "validExamples": valid_examples,
    }


def build_sections() -> list[dict]:
    return [
        build_method_section(
            section_id="indexing-and-slices",
            title="Indexing, Slices, and Slice Assignment",
            summary="Lists and strings support indexed access, half-open slices, optional step traversal, and list slice replacement.",
            tags=["indexing", "slices", "lists", "strings", "assignment"],
            constructs=["value[index]", "value[start:end]", "value[start:end:step]", "list_slice = replacement"],
            query_hints=["list indexing", "string slicing", "reverse slices", "slice assignment"],
            syntax_patterns=[
                "items[0]",
                "items[1:]",
                "items[::2]",
                "items[4:0:-1]",
                "items[1:3] = [20, 30]",
            ],
            rules=[
                "Slice bounds are start-inclusive and end-exclusive; either bound may be omitted.",
                "A negative bound counts from the end and a negative step traverses backwards.",
                "A slice step may not be zero; a missing step defaults to 1.",
                "List slice assignment accepts a list and may resize the list when the step is 1.",
                "Extended slice assignment with a non-unit step requires an equal-length replacement list.",
                "Strings are immutable and cannot be assigned through a slice.",
            ],
            tables=[
                {
                    "title": "Slice forms",
                    "columns": ["Form", "Meaning", "Example"],
                    "rows": [
                        ["value[index]", "One element", "items[0]"],
                        ["value[start:end]", "Forward half-open range", "items[1:3]"],
                        ["value[start:end:step]", "Stepped range", "items[::2]"],
                        ["list[start:end] = list", "Replace/delete list range", "items[1:2] = [\"new\"]"],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Stepped reads and replacement",
                    "code": [
                        "let values = [0, 1, 2, 3, 4, 5];",
                        "let even = values[::2];",
                        "let reverse = values[5:0:-2];",
                        "values[1:3] = [10, 20, 30];",
                    ],
                    "notes": ["Use an equal-length replacement for non-unit steps."],
                }
            ],
        ),
        build_method_section(
            section_id="collection-comprehensions",
            title="List and Dictionary Comprehensions",
            summary="Compact derived collections over lists, sets, maps (by key), and strings with optional filters and nested clauses.",
            tags=["comprehensions", "lists", "dictionaries", "sets"],
            constructs=["[expression for item in iterable]", "{key: value for item in iterable}"],
            query_hints=["list comprehension", "dictionary comprehension", "comprehension filter"],
            syntax_patterns=[
                "[x * 2 for x in values if x > 1]",
                "{x: x for x in \"ab\"}",
            ],
            rules=[
                "List and dictionary comprehensions accept lists, sets, maps (iterating keys), and strings as iterables.",
                "String iteration binds one-character string values.",
                "Filters use normal Versa truthiness and nested clauses are evaluated left to right.",
                "Unsupported scalar iterables raise a runtime error instead of silently producing an empty result.",
            ],
            tables=[],
            valid_examples=[
                {
                    "title": "Filtered list and dictionary comprehensions",
                    "code": [
                        "let doubled = [x * 2 for x in [1, 2, 3] if x > 1];",
                        "let letters = {x: x for x in \"ab\"};",
                    ],
                    "notes": [],
                }
            ],
        ),
        build_method_section(
            section_id="builtins-runtime-inventory",
            title="Built-ins, Special Forms, and Runtime Globals Inventory",
            summary="Exact runtime-provided built-ins, special forms, and global surfaces exposed by the evaluator before any user code runs.",
            tags=["builtins", "globals", "runtime", "special forms"],
            constructs=["print", "input", "exit", "AsFloat", "int", "float", "str", "bool", "range", "len", "leng", "join", "set", "map", "filter", "any", "all", "sum", "reduce", "json", "xml", "type", "is_type", "is_unset", "env", "unset"],
            query_hints=["all builtins", "runtime globals", "is_unset", "json builtin", "xml builtin"],
            syntax_patterns=[
                "print(`Hello {name}`);",
                "let ids = range(1, 4);",
                "let raw = json(\"{\\\"ok\\\":true}\");",
                "let missing = is_unset(optionalName);",
            ],
            rules=[
                "Built-ins are available without imports.",
                "is_unset(identifier) is a special identifier-only call, not a normal value call.",
                "json(value) and xml(value) accept either a string to parse or a value that is already recognized as that structured type.",
                "env is injected as an object containing process environment variables.",
                "unset exists as a runtime sentinel value.",
            ],
            tables=[
                {
                    "title": "Core built-ins and globals",
                    "columns": ["Name", "Shape", "Returns", "Notes"],
                    "rows": [
                        ["print", "print(value, ...);", "null", "Prints every argument and adds a newline."],
                        ["input", "input(prompt?);", "string", "Reads one line exactly as typed."],
                        ["exit", "exit(code?);", "never", "Throws ExitException; default code is 0."],
                        ["AsFloat", "AsFloat(value);", "float", "One-argument float coercion helper."],
                        ["int", "int(value);", "int", "Rejects null and non-numeric text."],
                        ["float", "float(value);", "float", "Rejects null and non-numeric text."],
                        ["str", "str(value);", "string", "Uses the runtime display formatter."],
                        ["bool", "bool(value);", "bool", "One-argument boolean coercion helper."],
                        ["range", "range(end); range(start, end); range(start, end, step);", "list<int>", "Ranges stop before end; a non-zero step controls direction and spacing."],
                        ["len", "len(value);", "int", "Conventional length helper for lists, strings, maps, and sets."],
                        ["leng", "leng(value);", "int", "Historical spelling retained as an alias for len."],
                        ["join", "join(separator, iterable);", "string", "Stringifies members from a list, set, map (keys), or string with the runtime formatter."],
                        ["set", "set(); set(list); set(value, ...);", "set", "Builds a linked-hash set and preserves insertion order."],
                        ["map", "map(callable, iterable);", "list", "Calls the callable once per element of a list, set, map (keys), or string and collects the results."],
                        ["filter", "filter(predicate, iterable);", "list", "Keeps elements from a list, set, map (keys), or string for which the callable predicate is truthy."],
                        ["any", "any(iterable);", "bool", "Returns true when at least one iterable member is truthy; empty iterables return false."],
                        ["all", "all(iterable);", "bool", "Returns true when every iterable member is truthy; empty iterables return true."],
                        ["sum", "sum(iterable, initial?);", "number", "Sums numeric members and preserves an integer result when possible."],
                        ["reduce", "reduce(reducer, iterable, initial?);", "any", "Folds an iterable left-to-right; an initial value is required for an empty iterable."],
                        ["json", "json(jsonTextOrValue);", "json value", "Parses a JSON string or passes through an already-recognized json value."],
                        ["xml", "xml(xmlTextOrValue);", "xml value", "Parses an XML string or passes through an already-recognized xml value."],
                        ["type", "type(value);", "string", "Returns the runtime type label."],
                        ["is_type", "is_type(value, expected);", "bool", "Normalizes aliases such as array->list and integer->int."],
                        ["is_unset", "is_unset(identifier);", "bool", "Requires a bare identifier, not a quoted name or arbitrary expression."],
                        ["env", "env.KEY", "object", "Process environment map injected into every evaluator."],
                        ["unset", "unset", "sentinel", "Runtime sentinel value used for unset bindings."],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Built-ins and globals in one script",
                    "code": [
                        "let ids = range(1, 4);",
                        "let encoded = json(\"{\\\"ids\\\":[1,2,3]}\");",
                        "print(type(ids));",
                        "print(join(\", \", [str(ids[0]), str(ids[1]), str(ids[2])]));",
                        "print(is_unset(optional_name));",
                        "print(env.HOME ?? \"no-home\");",
                    ],
                    "notes": [
                        "The built-ins do not require imports.",
                        "is_unset uses a bare identifier.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="string-list-map-set-member-methods",
            title="String, List, Map, Entry, and Set Member Methods",
            summary="Native member methods exposed by the evaluator for strings and collection-like runtime values.",
            tags=["members", "string methods", "list methods", "map methods", "set methods"],
            constructs=["split", "upper", "trim", "keys", "items", "add", "union", "swap"],
            query_hints=["string methods", "list methods", "set methods", "map items", "entry value"],
            syntax_patterns=[
                "\"alpha beta\".split(\" \")",
                "items.keys()",
                "tags.add(\"urgent\")",
                "numbers.swap(0, 2)",
            ],
            rules=[
                "These methods are resolved by MemberAccessEvaluator and StringEvaluator, not by module imports.",
                "Map items() returns Entry values with dot, bracket, and method access.",
                "Set helpers return booleans, sets, or null depending on the operation; mutating helpers change the original set.",
                "List helpers mutate the list for add, remove, clear, reverse, insert, swap, and sort.",
            ],
            tables=[
                {
                    "title": "String methods",
                    "columns": ["Method", "Returns", "Notes"],
                    "rows": [
                        ["split(sep?)", "list<string>", "Default separator is a single space string."],
                        ["splitlines()", "list<string>", "Splits on line boundaries."],
                        ["toUpper()/upper()", "string", "Uppercase aliases."],
                        ["toLower()/lower()/casefold()", "string", "Lowercase aliases."],
                        ["capitalize()/capitalise()", "string", "Capitalizes the first character and lowers the rest."],
                        ["title()", "string", "Title-cases whitespace-separated words."],
                        ["trim()/strip()", "string", "Trims both ends."],
                        ["lstrip()/rstrip()", "string", "Trim-left and trim-right variants."],
                        ["contains(value)", "bool", "Substring containment."],
                        ["startswith()/starts_with()", "bool", "Prefix aliases."],
                        ["endswith()/ends_with()", "bool", "Suffix aliases."],
                        ["replace(old, new)", "string", "Replaces every occurrence."],
                        ["count(value)", "int", "Empty needle returns length + 1."],
                        ["find(value)", "int", "Returns -1 when not found."],
                        ["index(value)", "int", "Throws when not found."],
                        ["isalpha()/isdigit()/isalnum()/isspace()", "bool", "Character-class predicates."],
                        ["islower()/isupper()", "bool", "Require at least one letter."],
                        ["message", "string", "Direct member access returns the string itself."],
                    ],
                },
                {
                    "title": "Map, Entry, list, and set methods",
                    "columns": ["Type", "Methods", "Notes"],
                    "rows": [
                        ["map/object", "keys, values, items, update, pop, clear", "items() returns Entry values."],
                        ["Entry", "key, value, k, v", "entry.key and entry.value also work as direct fields."],
                        ["list", "add, remove, remove_all, clear, sort, reverse, insert, pop, index, all_indexes, count, contains, size, get, join, swap", "All list member methods are evaluator-side helpers."],
                        ["set", "add, remove, discard, contains/has, clear, size/len, to_list/values, copy, update/union_update, union, intersection, difference, symmetric_difference, is_subset/issubset, is_superset/issuperset, equals, pop", "Sets preserve insertion order because the runtime uses a linked-hash set."],
                    ],
                },
            ],
            valid_examples=[
                {
                    "title": "Native collection member methods",
                    "code": [
                        "let title = \"shoe repair queue\".title();",
                        "let numbers = [1, 2, 3];",
                        "numbers.swap(0, 2);",
                        "let record = {job: \"sole replacement\", price: 250};",
                        "for (entry in record.items()) {",
                        "  print(`${entry.key()}: {entry.value()}`);",
                        "}",
                        "let tags = set([\"repair\", \"urgent\"]);",
                        "print(tags.union([\"paid\"]));",
                    ],
                    "notes": [
                        "These helpers are available without module imports.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="http-module-reference",
            title="`http` Module Reference",
            summary="Exact evaluator-exposed HTTP methods and the supported option families used to build request headers, query strings, auth, and bodies.",
            tags=["module", "http", "networking"],
            constructs=["http.request", "http.get", "http.post", "http.put", "http.patch", "http.delete"],
            query_hints=["http module methods", "http auth options", "http body options"],
            syntax_patterns=[
                "http.request(\"GET\", url, {query: {page: 1}});",
                "http.post(url, {headers: {Accept: \"application/json\"}, body: {ok: true}});",
            ],
            rules=[
                "All exposed HTTP calls are synchronous from Versa and return a normalized response map.",
                "GET and HEAD requests send no body.",
                "When body is present and no Content-Type is supplied, the runtime defaults to application/json.",
                "form and bodyBytesBase64 take precedence over body when supplied.",
            ],
            tables=[
                {
                    "title": "HTTP methods",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["request", "http.request(method, url, options={})", "object", "General entry point; method is uppercased internally."],
                        ["get", "http.get(url, options={})", "object", "Convenience wrapper for GET."],
                        ["post", "http.post(url, options={})", "object", "Convenience wrapper for POST."],
                        ["put", "http.put(url, options={})", "object", "Convenience wrapper for PUT."],
                        ["patch", "http.patch(url, options={})", "object", "Convenience wrapper for PATCH."],
                        ["delete", "http.delete(url, options={})", "object", "Convenience wrapper for DELETE."],
                    ],
                },
                {
                    "title": "Supported option keys",
                    "columns": ["Option", "Shape", "Behavior"],
                    "rows": [
                        ["headers", "object", "Request headers copied as strings."],
                        ["query", "object", "Merged into the final query string."],
                        ["body", "object/list/string/scalar", "Serialized as JSON text when no form or raw bytes override is present."],
                        ["form", "object", "Serialized as application/x-www-form-urlencoded."],
                        ["bodyBytesBase64", "base64 string", "Decoded and sent as raw bytes."],
                        ["timeoutSeconds", "number", "Minimum effective timeout is 1 second."],
                        ["authHeader", "string", "Applied to Authorization if not already set."],
                        ["authBearer/authToken", "string", "Converted to Authorization: Bearer <token>."],
                        ["authBasic", "object", "Needs username and password."],
                        ["authOAuth2", "object", "Uses token/accessToken and optional tokenType."],
                        ["authApiKey", "object", "Can place the key in headers or query params."],
                        ["authDigest", "object", "Digest helper supported by the HTTP module."],
                        ["auth", "string or object", "Generic auth dispatcher that routes by type."],
                    ],
                },
            ],
            valid_examples=[
                {
                    "title": "POST JSON with bearer auth",
                    "code": [
                        "http import *;",
                        "let response = http.post(\"https://api.example.com/jobs\", {",
                        "  authBearer: env.API_TOKEN,",
                        "  headers: {Accept: \"application/json\"},",
                        "  body: {status: \"queued\", count: 3}",
                        "});",
                        "print(response.status);",
                    ],
                    "notes": [
                        "The body is JSON-serialized by default.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="json-xml-module-reference",
            title="`json_xml` Module Reference",
            summary="Full JSON, XML, and text helper surface injected as the `json_xml` module.",
            tags=["module", "json_xml", "json", "xml"],
            constructs=["parse_json", "to_json", "parse_xml", "json_to_xml", "xml_to_json", "read_text"],
            query_hints=["json_xml methods", "xml conversion", "write_json", "parse_xml"],
            syntax_patterns=[
                "json_xml.parse_json(raw);",
                "json_xml.write_json(\"scratch/out.json\", payload, true);",
                "json_xml.obj_to_xml(payload, \"job\");",
            ],
            rules=[
                "parse_json and parse_xml throw runtime errors when the input text is invalid.",
                "to_json and obj_to_json are equivalent exports.",
                "json_to_xml and obj_to_xml default the root element name to root when no name is supplied.",
                "read_* and write_* helpers operate on UTF-8 text files.",
            ],
            tables=[
                {
                    "title": "`json_xml` exports",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["parse_json", "json_xml.parse_json(text)", "value", "Parses JSON text into Versa runtime values."],
                        ["obj_to_json", "json_xml.obj_to_json(value, pretty=false)", "string", "JSON serializer."],
                        ["to_json", "json_xml.to_json(value, pretty=false)", "string", "Alias of obj_to_json."],
                        ["read_json", "json_xml.read_json(path)", "value", "Reads then parses JSON."],
                        ["write_json", "json_xml.write_json(path, value, pretty=false)", "string", "Writes JSON and returns the path."],
                        ["parse_xml", "json_xml.parse_xml(text)", "object", "Returns a wrapped XML object rooted at root/name/attributes/children/text."],
                        ["read_xml", "json_xml.read_xml(path)", "object", "Reads then parses XML."],
                        ["write_xml", "json_xml.write_xml(path, xmlText)", "string", "Writes XML text and returns the path."],
                        ["json_to_xml", "json_xml.json_to_xml(value, rootName=\"root\")", "string", "Converts a generic value to XML text."],
                        ["obj_to_xml", "json_xml.obj_to_xml(value, rootName=\"root\")", "string", "Accepts either a generic object or an existing XML wrapper map."],
                        ["xml_to_json", "json_xml.xml_to_json(xmlText)", "value", "Parses XML and returns the root payload."],
                        ["read_text", "json_xml.read_text(path)", "string", "Raw UTF-8 file read."],
                        ["write_text", "json_xml.write_text(path, text)", "string", "Raw UTF-8 file write."],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Round-trip JSON and XML",
                    "code": [
                        "json_xml import *;",
                        "let payload = {job: \"heel repair\", price: 180};",
                        "let jsonText = json_xml.to_json(payload, true);",
                        "let xmlText = json_xml.obj_to_xml(payload, \"repair\");",
                        "print(json_xml.parse_json(jsonText).job);",
                        "print(json_xml.xml_to_json(xmlText).job);",
                    ],
                    "notes": [
                        "The same module covers JSON, XML, and raw text helpers.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="filer-module-reference",
            title="`filer` Module Reference",
            summary="Filesystem helpers exposed through the `filer` module for paths, directories, text, JSON, XML, bytes, and CSV.",
            tags=["module", "filer", "filesystem"],
            constructs=["join", "ensure_dir", "exists", "write_text", "read_csv_records"],
            query_hints=["filer methods", "csv helpers", "filesystem module"],
            syntax_patterns=[
                "filer.join(\"scratch\", \"jobs\", \"queue.json\")",
                "filer.write_json(path, payload, true)",
            ],
            rules=[
                "filer writes create parent directories when needed.",
                "read_bytes_base64 returns the file contents encoded as base64 text.",
                "read_csv returns row arrays, while read_csv_records returns a record-oriented object wrapper.",
            ],
            tables=[
                {
                    "title": "`filer` exports",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["join", "filer.join(...parts)", "string", "Joins path fragments using the host filesystem separator."],
                        ["ensure_dir", "filer.ensure_dir(path)", "string", "Creates the directory tree and returns the path."],
                        ["exists", "filer.exists(path)", "bool", "Checks file or directory existence."],
                        ["write_text", "filer.write_text(path, text)", "string", "Writes UTF-8 text and returns the path."],
                        ["read_text", "filer.read_text(path)", "string", "Reads UTF-8 text."],
                        ["read_bytes_base64", "filer.read_bytes_base64(path)", "string", "Reads binary bytes and base64-encodes them."],
                        ["write_json", "filer.write_json(path, value, pretty=false)", "string", "Writes JSON text."],
                        ["read_json", "filer.read_json(path)", "value", "Reads and parses JSON."],
                        ["write_xml", "filer.write_xml(path, xmlText)", "string", "Writes XML text."],
                        ["read_xml", "filer.read_xml(path)", "object", "Reads and parses XML."],
                        ["write_csv", "filer.write_csv(path, rows)", "string", "Writes CSV rows."],
                        ["read_csv", "filer.read_csv(path)", "list", "Reads CSV into row arrays."],
                        ["read_csv_records", "filer.read_csv_records(path)", "object", "Reads CSV into a records-style object wrapper."],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Save a report to scratch",
                    "code": [
                        "filer import *;",
                        "let outDir = filer.join(\"scratch\", \"shoe-repair\");",
                        "filer.ensure_dir(outDir);",
                        "let outPath = filer.join(outDir, \"inventory.json\");",
                        "filer.write_json(outPath, {count: 3}, true);",
                        "print(filer.read_text(outPath));",
                    ],
                    "notes": [
                        "filer handles both path joining and structured file writes.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="email-module-reference",
            title="`email` Module Reference",
            summary="SMTP email sending surface exposed through the `email` module.",
            tags=["module", "email", "smtp"],
            constructs=["email.send"],
            query_hints=["email module", "smtp options", "send email"],
            syntax_patterns=["email.send({host: ..., port: ..., to: ...})"],
            rules=[
                "email exposes a single send(options) entry point.",
                "The options map can use either auth or username/password credentials.",
                "The result is a normalized delivery response envelope.",
            ],
            tables=[
                {
                    "title": "`email` exports and options",
                    "columns": ["Method or option", "Shape", "Notes"],
                    "rows": [
                        ["send", "email.send(options)", "Sends one SMTP message and returns a structured result map."],
                        ["host / port", "string / number", "SMTP server address and port."],
                        ["ssl / startTls", "bool", "Transport security flags."],
                        ["auth / username / password", "object or strings", "Authentication credentials."],
                        ["from / to", "string or list", "Sender and recipient fields."],
                        ["subject", "string", "Message subject."],
                        ["text / html", "string", "Plain-text and HTML body variants."],
                        ["timeoutMs", "number", "Delivery timeout in milliseconds."],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Send a text email",
                    "code": [
                        "email import *;",
                        "let result = email.send({",
                        "  host: env.SMTP_HOST,",
                        "  port: 587,",
                        "  startTls: true,",
                        "  username: env.SMTP_USER,",
                        "  password: env.SMTP_PASS,",
                        "  from: \"ops@example.com\",",
                        "  to: [\"owner@example.com\"],",
                        "  subject: \"Repairs queued\",",
                        "  text: \"Three shoes are ready for pickup.\"",
                        "});",
                        "print(result.status);",
                    ],
                    "notes": ["Use html instead of text when you need an HTML message body."],
                }
            ],
        ),
        build_method_section(
            section_id="crypto-module-reference",
            title="`crypto` Module Reference",
            summary="Full hashing, HMAC, encoding, random, key-derivation, and AES-GCM surface exposed through the `crypto` module.",
            tags=["module", "crypto", "hashing", "encryption"],
            constructs=["sha256", "hmac_sha256", "base64_encode", "pbkdf2", "aes_gcm_encrypt"],
            query_hints=["crypto methods", "pbkdf2", "aes gcm", "uuid", "base64url"],
            syntax_patterns=[
                "crypto.sha256(\"text\")",
                "crypto.pbkdf2(password, salt, 100000, 32, \"HmacSHA256\")",
                "crypto.aes_gcm_encrypt(plaintext, key, iv?)",
            ],
            rules=[
                "crypto exports are evaluator-side wrappers over the Java runtime implementation.",
                "pbkdf2 defaults to 100000 iterations, 32-byte keys, and HmacSHA256 when optional arguments are omitted.",
                "aes_gcm_encrypt returns a structured object containing ciphertext material, while aes_gcm_decrypt returns plaintext text.",
            ],
            tables=[
                {
                    "title": "`crypto` exports",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["sha256", "crypto.sha256(text)", "string", "Hex digest."],
                        ["sha512", "crypto.sha512(text)", "string", "Hex digest."],
                        ["hmac_sha256", "crypto.hmac_sha256(secret, message)", "string", "Hex HMAC digest."],
                        ["hmac_sha512", "crypto.hmac_sha512(secret, message)", "string", "Hex HMAC digest."],
                        ["base64_encode", "crypto.base64_encode(text)", "string", "Standard base64 output."],
                        ["base64_decode", "crypto.base64_decode(base64)", "string", "UTF-8 decoded text."],
                        ["base64url_encode", "crypto.base64url_encode(text)", "string", "Base64url output without standard alphabet."],
                        ["base64url_decode", "crypto.base64url_decode(base64url)", "string", "UTF-8 decoded text."],
                        ["random_hex", "crypto.random_hex(numBytes)", "string", "Random bytes rendered as hex."],
                        ["random_bytes", "crypto.random_bytes(numBytes)", "string", "Random bytes rendered as base64 text."],
                        ["uuid", "crypto.uuid()", "string", "Random UUID string."],
                        ["pbkdf2", "crypto.pbkdf2(password, salt, iterations=100000, keyLength=32, algorithm=\"HmacSHA256\")", "string", "Derived key rendered as base64 text."],
                        ["aes_gcm_encrypt", "crypto.aes_gcm_encrypt(plaintext, key, iv?)", "object", "Returns ciphertext metadata including IV when generated."],
                        ["aes_gcm_decrypt", "crypto.aes_gcm_decrypt(ciphertext, key, iv)", "string", "Decrypts AES-GCM ciphertext."],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Hash and encrypt",
                    "code": [
                        "crypto import *;",
                        "let digest = crypto.sha256(\"shoe-repair-job\");",
                        "let encrypted = crypto.aes_gcm_encrypt(\"ready\", env.APP_KEY);",
                        "let plain = crypto.aes_gcm_decrypt(encrypted.ciphertext, env.APP_KEY, encrypted.iv);",
                        "print(digest);",
                        "print(plain);",
                    ],
                    "notes": [
                        "AES-GCM encryption returns a structured object, not only a raw ciphertext string.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="jwt-module-reference",
            title="`jwt` Module Reference",
            summary="JWT signing, verification, and decode helpers exposed through the `jwt` module.",
            tags=["module", "jwt", "auth"],
            constructs=["jwt.sign", "jwt.verify", "jwt.decode"],
            query_hints=["jwt methods", "jwt sign", "jwt verify"],
            syntax_patterns=[
                "jwt.sign(payload, secret, {algorithm: \"HS256\"})",
                "jwt.verify(token, secret, {issuer: \"liwiro\"})",
            ],
            rules=[
                "jwt.sign requires the payload to be an object.",
                "jwt.verify returns a structured verification result object.",
                "Supported signing algorithms are HS256, HS384, and HS512.",
            ],
            tables=[
                {
                    "title": "`jwt` exports",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["sign", "jwt.sign(payloadObject, secret, options={})", "string", "Signs a JWT token string."],
                        ["verify", "jwt.verify(token, secret, options={})", "object", "Verifies a token and returns payload/metadata."],
                        ["decode", "jwt.decode(token)", "object", "Decodes without verifying the signature."],
                    ],
                },
                {
                    "title": "Common JWT option keys",
                    "columns": ["Option", "Notes"],
                    "rows": [
                        ["algorithm", "HS256, HS384, or HS512."],
                        ["issuer / audience / subject", "Standard JWT claim helpers."],
                        ["expiresInSeconds", "exp claim helper."],
                        ["notBeforeSeconds", "nbf claim helper."],
                    ],
                },
            ],
            valid_examples=[
                {
                    "title": "Sign and verify a token",
                    "code": [
                        "jwt import *;",
                        "let token = jwt.sign({user: \"zulan\"}, env.JWT_SECRET, {algorithm: \"HS256\", issuer: \"liwiro\"});",
                        "let verified = jwt.verify(token, env.JWT_SECRET, {issuer: \"liwiro\"});",
                        "print(verified.payload.user);",
                    ],
                    "notes": [
                        "jwt.decode(token) skips verification and is only for inspection.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="time-module-reference",
            title="`time` Module Reference",
            summary="Low-level clock, sleep, formatting, and time-struct helpers exposed through the `time` module.",
            tags=["module", "time", "clock"],
            constructs=["time.time", "time.sleep", "time.strftime", "time.ctime"],
            query_hints=["time module methods", "strftime", "ctime", "time struct"],
            syntax_patterns=[
                "let stamp = time.time();",
                "let struct = time.localtime();",
                "print(time.strftime(\"%Y-%m-%d\", struct));",
            ],
            rules=[
                "sleep expects non-negative seconds and may be fractional.",
                "strftime requires a format string and a time struct map; when omitted in the wrapper it defaults to localtime(now).",
                "ctime supports default, iso, full, and custom format modes.",
            ],
            tables=[
                {
                    "title": "`time` exports",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["time", "time.time()", "float", "Epoch seconds as a fractional number."],
                        ["time_ns", "time.time_ns()", "int", "Epoch nanoseconds."],
                        ["perf_counter", "time.perf_counter()", "float", "Monotonic performance timer."],
                        ["monotonic", "time.monotonic()", "float", "Alias-style monotonic timer."],
                        ["process_time", "time.process_time()", "float", "Current thread CPU time when supported."],
                        ["sleep", "time.sleep(seconds)", "null", "Sleeps for the requested duration."],
                        ["localtime", "time.localtime(timestamp?)", "object", "Returns a time struct in the system timezone."],
                        ["gmtime", "time.gmtime(timestamp?)", "object", "Returns a UTC time struct."],
                        ["strftime", "time.strftime(format, timeStruct?)", "string", "Formats a time struct."],
                        ["ctime", "time.ctime(timestamp?, format?, customPattern?)", "string", "Supports default, iso, full, custom, and direct pattern strings."],
                    ],
                },
                {
                    "title": "Time struct fields",
                    "columns": ["Field", "Meaning"],
                    "rows": [
                        ["year, month, day", "Calendar date components."],
                        ["hour, minute, second", "Clock components."],
                        ["weekday, yearday", "Weekday and day-of-year values."],
                        ["timezone, offset_seconds", "Timezone label and offset metadata."],
                    ],
                },
            ],
            valid_examples=[
                {
                    "title": "Format local time",
                    "code": [
                        "time import *;",
                        "let now = time.localtime();",
                        "print(time.strftime(\"%Y-%m-%d %H:%M:%S\", now));",
                        "print(time.ctime(null, \"iso\"));",
                    ],
                    "notes": ["Pass null as the timestamp to use the current instant."],
                }
            ],
        ),
        build_method_section(
            section_id="datetime-module-reference",
            title="`datetime` Module Reference",
            summary="Date/time constructors, timezone helpers, timedelta constructors, and the helper methods supported on returned datetime-like values.",
            tags=["module", "datetime", "date", "timedelta", "timezone"],
            constructs=["datetime.now", "datetime.fromtimestamp", "datetime.date.today", "datetime.time.from_components", "datetime.timedelta", "datetime.timezone"],
            query_hints=["datetime module methods", "timedelta", "timezone", "isoformat", "human_readable"],
            syntax_patterns=[
                "let now = datetime.now();",
                "let due = now + datetime.timedelta({days: 2});",
                "print(due.isoformat());",
            ],
            rules=[
                "datetime.now and fromtimestamp return structured datetime values, not opaque Java objects.",
                "datetime.time.from_components validates hour/minute/second/microsecond bounds.",
                "datetime.timedelta accepts a map, a list, a number of seconds, or null.",
                "datetime.timezone accepts either offset seconds or a +HH:MM/-HH:MM string.",
            ],
            tables=[
                {
                    "title": "`datetime` exports",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["now", "datetime.now()", "datetime value", "Current local datetime wrapper."],
                        ["fromtimestamp", "datetime.fromtimestamp(ts)", "datetime value", "Local datetime from epoch timestamp."],
                        ["date.today", "datetime.date.today()", "date value", "Current local date wrapper."],
                        ["date.fromtimestamp", "datetime.date.fromtimestamp(ts)", "date value", "Date from epoch timestamp."],
                        ["time.from_components", "datetime.time.from_components(hour, minute, second, microsecond)", "time value", "Validated time wrapper."],
                        ["timedelta", "datetime.timedelta(value)", "timedelta value", "Accepts map, list, number, or null."],
                        ["timezone", "datetime.timezone(offsetSecondsOrString)", "timezone value", "Accepts offset seconds or +HH:MM/-HH:MM."],
                    ],
                },
                {
                    "title": "Helper methods on returned values",
                    "columns": ["Value type", "Methods", "Notes"],
                    "rows": [
                        ["datetime", "isoformat(), human(format?), human_readable(format?)", "Supports + and - with timedelta and subtraction from another datetime."],
                        ["date", "isoformat(), human(format?), human_readable(format?)", "Date-specific display helpers."],
                        ["time", "isoformat(), human(format?), human_readable(format?)", "Time-specific display helpers."],
                        ["timedelta", "total_seconds(), human(), human_readable()", "Duration helpers."],
                        ["timezone", "isoformat(), human(), human_readable()", "Offset and label helpers."],
                    ],
                },
            ],
            valid_examples=[
                {
                    "title": "Datetime arithmetic and helpers",
                    "code": [
                        "datetime import *;",
                        "let start = datetime.now();",
                        "let delay = datetime.timedelta({hours: 2, minutes: 30});",
                        "let end = start + delay;",
                        "print(end.isoformat());",
                        "print(delay.total_seconds());",
                    ],
                    "notes": [
                        "datetime and timedelta values participate in evaluator-side arithmetic.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="random-module-reference",
            title="`random` Module Reference",
            summary="All random-number, sampling, shuffle, and probability helpers exposed through the `random` module.",
            tags=["module", "random", "sampling"],
            constructs=["seed", "random", "randint", "randints", "randrange", "uniform", "choice", "choices", "shuffle", "sample", "boolean", "chance"],
            query_hints=["random module methods", "randrange", "shuffle", "sample", "chance"],
            syntax_patterns=[
                "random.seed(42);",
                "let pick = random.choice(items);",
                "let ok = random.chance(0.75);",
            ],
            rules=[
                "seed accepts null or a seed value and mutates the module's shared random state.",
                "randint is inclusive on both ends.",
                "randrange supports one-argument and two/three-argument forms through the evaluator wrapper.",
                "shuffle mutates the input list and returns the same list reference.",
            ],
            tables=[
                {
                    "title": "`random` exports",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["seed", "random.seed(value?)", "null", "Reseeds the shared RNG."],
                        ["random", "random.random()", "float", "Uniform value in [0, 1)."],
                        ["randint", "random.randint(min, max)", "int", "Inclusive range."],
                        ["randints", "random.randints(min, max, count)", "list<int>", "Repeated inclusive draws."],
                        ["randrange", "random.randrange(stop) or random.randrange(start, stop, step?)", "int", "Step defaults to 1."],
                        ["uniform", "random.uniform(min, max)", "float", "Uniform float in range."],
                        ["choice", "random.choice(list)", "value", "Single element from a list."],
                        ["choices", "random.choices(list, count=1)", "list", "Repeated draws with replacement."],
                        ["shuffle", "random.shuffle(list)", "list", "Mutates and returns the original list."],
                        ["sample", "random.sample(list, count)", "list", "Unique sample without replacement."],
                        ["boolean", "random.boolean()", "bool", "Random true/false."],
                        ["chance", "random.chance(probability)", "bool", "Probability must be between 0 and 1."],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Sample repair jobs",
                    "code": [
                        "random import *;",
                        "let jobs = [\"sole\", \"zip\", \"heel\", \"polish\"];",
                        "random.seed(42);",
                        "print(random.sample(jobs, 2));",
                        "print(random.chance(0.6));",
                    ],
                    "notes": ["Use sample for unique picks and choices for repeated picks with replacement."],
                }
            ],
        ),
        build_method_section(
            section_id="vdb-bridge-global-reference",
            title="`vdb` Bridge Global Reference",
            summary="Full global `vdb` bridge surface exposed by MemberAccessEvaluator, including auth, context, CRUD, indexes, scripts, jobs, transactions, aggregation, TUMI, and model binding.",
            tags=["module", "vdb", "database", "bridge"],
            constructs=["vdb.auth", "vdb.use", "vdb.collection", "vdb.execute_script", "vdb.schedule_job", "vdb.tumi"],
            query_hints=["all vdb methods", "vdb auth", "vdb scripts", "vdb jobs", "vdb indexes", "tumi"],
            syntax_patterns=[
                "vdb.auth({user: \"zulan\", pass: \"secret\"});",
                "vdb.use({domain: \"liwiro\", db: \"main\"});",
                "let parts = vdb.collection(\"parts\");",
            ],
            rules=[
                "All `vdb` methods other than auth and config require an authenticated VDB session.",
                "The bridge returns a normalized response envelope with ok, status, operation, message, data, error, and context fields.",
                "set and use accept domain with db or database aliases.",
                "Wrong credentials surface VDBAuthenticationException; missing auth surfaces VDBNotAuthenticatedException.",
            ],
            tables=[
                {
                    "title": "Auth, context, and metadata",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["auth", "vdb.auth({user, pass})", "object", "Starts or refreshes the authenticated VDB session."],
                        ["config", "vdb.config(); vdb.config({logging: true|false});", "object", "Reads or updates bridge logging flags; logs and logging are accepted."],
                        ["set", "vdb.set({domain, db|database})", "object", "Sets the active domain/database context."],
                        ["use", "vdb.use({domain, db|database})", "object", "Same context intent as set; validates domain/db existence."],
                        ["define", "vdb.define({...})", "object", "Defines domain/db metadata through the bridge."],
                        ["list_domains", "vdb.list_domains()", "object", "Lists domains."],
                        ["list_databases", "vdb.list_databases()", "object", "Lists databases in the current domain."],
                        ["list_collections", "vdb.list_collections()", "object", "Lists collections in the current database."],
                        ["drop", "vdb.drop(collectionOrPayload)", "object", "Drops a collection or context target, depending on payload."],
                        ["model", "vdb.model(classRef)", "object", "Registers a Versa class against a VDB collection binding."],
                        ["collection", "vdb.collection(name)", "collection handle", "Returns a collection wrapper with collection-scoped methods."],
                    ],
                },
                {
                    "title": "CRUD, aggregation, and index operations",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["insert", "vdb.insert(collection, doc)", "object", "Collection-agnostic insert wrapper."],
                        ["find", "vdb.find(collection, query, limit?)", "object", "Collection-agnostic find wrapper."],
                        ["update", "vdb.update(collection, query, patch)", "object", "Collection-agnostic update wrapper."],
                        ["delete", "vdb.delete(collection, query)", "object", "Collection-agnostic delete wrapper."],
                        ["aggregate", "vdb.aggregate(collection, pipeline)", "object", "Runs an aggregation pipeline."],
                        ["create_index", "vdb.create_index(collection, field, unique=false)", "object", "Creates an index."],
                        ["drop_index", "vdb.drop_index(collection, field)", "object", "Drops an index."],
                        ["list_indexes", "vdb.list_indexes(collection)", "object", "Lists indexes for a collection."],
                        ["rebuild_indexes", "vdb.rebuild_indexes(collection)", "object", "Rebuilds collection indexes."],
                        ["index_advisor_status", "vdb.index_advisor_status()", "object", "Reads advisor status for the current domain/db."],
                        ["index_advisor_apply", "vdb.index_advisor_apply(limit?)", "object", "Applies recommended indexes."],
                        ["index_advisor_policy", "vdb.index_advisor_policy(mode?)", "object", "Reads or sets advisor policy: auto, manual, off."],
                        ["index_advisor_remove_auto_indexes", "vdb.index_advisor_remove_auto_indexes()", "object", "Removes advisor-created auto indexes."],
                    ],
                },
                {
                    "title": "Scripts, jobs, transactions, and RBAC",
                    "columns": ["Method", "Signature", "Returns", "Notes"],
                    "rows": [
                        ["save_script", "vdb.save_script(name, service, code)", "object", "Stores a Versa script in VDB."],
                        ["load_script", "vdb.load_script(name)", "object", "Loads a stored script."],
                        ["delete_script", "vdb.delete_script(name)", "object", "Deletes a stored script."],
                        ["execute_script", "vdb.execute_script(name, params={})", "object", "Executes a stored script through the bridge."],
                        ["list_scripts", "vdb.list_scripts()", "object", "Lists stored script names/metadata."],
                        ["schedule_job", "vdb.schedule_job({name, script, start_at?, every_seconds?, params?})", "object", "Creates an in-memory scheduled script job."],
                        ["list_jobs", "vdb.list_jobs()", "object", "Lists scheduled jobs."],
                        ["cancel_job", "vdb.cancel_job(name)", "object", "Cancels a scheduled job."],
                        ["begin_transaction", "vdb.begin_transaction()", "object", "Begins a transaction."],
                        ["commit_transaction", "vdb.commit_transaction()", "object", "Commits the active transaction."],
                        ["abort_transaction", "vdb.abort_transaction()", "object", "Aborts the active transaction."],
                        ["tumi", "vdb.tumi(payload)", "object", "Forwards RBAC/TUMI commands to VDB."],
                    ],
                },
                {
                    "title": "Normalized response envelope",
                    "columns": ["Field", "Meaning"],
                    "rows": [
                        ["ok", "Boolean success flag."],
                        ["status", "success, error, or not_found."],
                        ["operation", "Bridge operation name."],
                        ["message", "Human-readable result text."],
                        ["data", "Operation payload."],
                        ["error", "Error detail when present."],
                        ["context", "Domain, database, collection, timestamp, and operation metadata."],
                    ],
                },
            ],
            valid_examples=[
                {
                    "title": "Authenticate, switch context, and query a collection",
                    "code": [
                        "vdb.auth({user: env.VDB_USER, pass: env.VDB_PASS});",
                        "vdb.use({domain: \"liwiro\", db: \"main\"});",
                        "let res = vdb.find(\"repairs\", {status: \"queued\"}, 10);",
                        "print(res.status);",
                    ],
                    "notes": [
                        "Call auth before any non-config bridge operation.",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="vdb-collection-and-model-reference",
            title="VDB Collection, Class, and Instance Method Reference",
            summary="Evaluator-exposed methods on collection handles, VDB-bound Versa classes, and persisted Versa instances.",
            tags=["vdb", "collection handle", "class binding", "instance methods"],
            constructs=["collection.insert", "Class.find_many", "Class.create", "instance.save", "instance.reload"],
            query_hints=["vdb collection methods", "vdb class methods", "vdb instance methods"],
            syntax_patterns=[
                "let repairs = vdb.collection(\"repairs\");",
                "let Repair = vdb.model(RepairJob);",
                "let row = Repair.create({status: \"queued\"});",
            ],
            rules=[
                "Collection handles expose collection-scoped CRUD and index helpers.",
                "Versa classes bound through vdb.model(...) expose static data-access helpers.",
                "Persisted instances expose save/update/delete/reload plus schema and field access helpers.",
            ],
            tables=[
                {
                    "title": "Collection handle methods",
                    "columns": ["Method", "Signature", "Notes"],
                    "rows": [
                        ["insert", "collection.insert(doc)", "Insert into the bound collection."],
                        ["find", "collection.find(query, limit?)", "Query the bound collection."],
                        ["update", "collection.update(query, patch)", "Update matching documents."],
                        ["delete", "collection.delete(query)", "Delete matching documents."],
                        ["create_index", "collection.create_index(field, unique=false)", "Create a collection index."],
                        ["drop_index", "collection.drop_index(field)", "Drop a collection index."],
                        ["list_indexes", "collection.list_indexes()", "List collection indexes."],
                        ["rebuild_indexes", "collection.rebuild_indexes()", "Rebuild collection indexes."],
                    ],
                },
                {
                    "title": "VDB-bound class methods",
                    "columns": ["Method", "Signature", "Notes"],
                    "rows": [
                        ["name/class_name", "Class.name or Class.class_name", "Class metadata."],
                        ["collection/collection_name", "Class.collection", "Resolved collection name."],
                        ["binding_info/meta", "Class.binding_info()", "Binding metadata."],
                        ["schema/schema_defaults", "Class.schema()", "Schema map."],
                        ["new/build/construct", "Class.new(...)", "Create an unsaved instance."],
                        ["find", "Class.find(query={})", "Find one instance."],
                        ["find_by_id", "Class.find_by_id(id)", "Find one by id."],
                        ["find_many/all", "Class.find_many(query={}, limit=100); Class.all(limit?)", "Find multiple instances."],
                        ["count", "Class.count(query={})", "Count matches."],
                        ["exists", "Class.exists(query={})", "Existence check."],
                        ["delete_many/delete_by_id", "Class.delete_many(query={}); Class.delete_by_id(id)", "Delete helpers."],
                        ["update_many", "Class.update_many(query={}, patch={})", "Bulk update helper."],
                        ["create", "Class.create(data={})", "Instantiate, assign, persist, and return an instance."],
                        ["from_object", "Class.from_object(data, persist=false)", "Build from raw data, optionally persisting."],
                        ["first_or_create", "Class.first_or_create(query={}, defaults={})", "Find or insert helper."],
                        ["upsert", "Class.upsert(query={}, patch={})", "Upsert helper."],
                    ],
                },
                {
                    "title": "Persisted instance methods",
                    "columns": ["Method", "Signature", "Notes"],
                    "rows": [
                        ["save", "instance.save()", "Persists the instance."],
                        ["update", "instance.update(patch={})", "Updates persisted fields."],
                        ["delete", "instance.delete()", "Deletes the backing row."],
                        ["reload/refresh", "instance.reload()", "Reloads from VDB."],
                        ["to_object", "instance.to_object()", "Returns a document map."],
                        ["assign", "instance.assign(patch={})", "Mutates fields without necessarily persisting yet."],
                        ["set/get", "instance.set(key, value); instance.get(key, fallback?)", "Field access helpers."],
                        ["clone", "instance.clone()", "Clones the instance."],
                        ["validate", "instance.validate()", "Runs schema validation."],
                        ["props_from_schema", "instance.props_from_schema()", "Applies schema defaults/properties."],
                        ["class_name/id/is_persisted", "instance.class_name, instance.id, instance.is_persisted", "Instance metadata."],
                    ],
                },
            ],
            valid_examples=[
                {
                    "title": "Collection and model-style access",
                    "code": [
                        "let repairs = vdb.collection(\"repairs\");",
                        "repairs.create_index(\"ticket_id\", true);",
                        "let rows = repairs.find({status: \"queued\"}, 5);",
                        "print(rows.status);",
                    ],
                    "notes": [
                        "Class-bound helpers depend on the vdb.model(...) binding flow, while collection handles only need vdb.collection(name).",
                    ],
                }
            ],
        ),
        build_method_section(
            section_id="agent-and-portal-operation-reference",
            title="Verse Agent, VI Portal, and VDB Portal Operation",
            summary="How Verse agents are expected to operate the VI and VDB surfaces now that location changes and page actions are direct rather than confirmation-driven.",
            tags=["verse agents", "vi portal", "vdb portal", "operations"],
            constructs=["vi-script artifact", "vdb-query artifact", "Run", "Save and Run", "Run Query"],
            query_hints=["agent capabilities", "vi portal actions", "vdb portal actions", "automatic location change"],
            syntax_patterns=[
                "artifact.kind = vi-script",
                "artifact.kind = vdb-query",
                "executeLabel = Run",
            ],
            rules=[
                "Verse agents should return direct VI or VDB artifacts instead of location-only placeholder artifacts.",
                "When the user runs a VI or VDB artifact from another page, Liwiro can switch workspaces automatically and continue the requested action there.",
                "VI drafts should prefer Run and Save and Run; VDB drafts should prefer Run Query.",
                "Redundant open/load labels are optional and should not be the default when the requested action is already executable.",
            ],
            tables=[
                {
                    "title": "Direct execution behavior",
                    "columns": ["Surface", "Artifact kind", "Primary action(s)", "Behavior"],
                    "rows": [
                        ["VI Portal", "vi-script", "Run, Save and Run", "Run executes the current draft buffer; Save and Run persists first, then executes."],
                        ["VDB Portal", "vdb-query", "Run Query", "Loads the prepared query into the editor and executes it through the portal."],
                        ["Service Builder", "service-builder-lapis", "Generate Service", "Opens or generates a validated service definition."],
                        ["Service Manager", "service-manager-action", "Start/Stop/Delete", "Runs the requested management action."],
                    ],
                }
            ],
            valid_examples=[
                {
                    "title": "Direct VI execution flow",
                    "code": [
                        "# User request: create a Versa CLI prototype",
                        "# Agent response: return artifact.kind = vi-script",
                        "# UI action: Run or Save and Run",
                    ],
                    "notes": [
                        "The agent should not stop at a location handoff when the prepared artifact is already executable.",
                    ],
                }
            ],
        ),
    ]


def augment_reference() -> dict:
    base = json.loads(read_text(REFERENCE_PATH))
    base = replace_reference_text(base, {
        "join(separator, list)": "join(separator, iterable)",
        "map(callable, list)": "map(callable, iterable)",
        "Core built-ins include print(...), input(prompt?), exit(code?), range(...), leng(value), join(separator, iterable), and map(callable, iterable).":
            "Core built-ins include print(...), input(prompt?), exit(code?), range(...), leng(value), join(separator, iterable), map(callable, iterable), filter(predicate, iterable), and reduce(reducer, iterable, initial?).",
    })
    evaluator_text = read_text(EVALUATOR_PATH)
    member_text = read_text(MEMBER_ACCESS_PATH)
    string_text = read_text(STRING_EVAL_PATH)

    ensure_expected("Evaluator built-ins", evaluator_text, ["environment.put(\"json\"", "environment.put(\"xml\"", "environment.put(\"time\"", "environment.put(\"random\""])
    ensure_expected("HTTP module", evaluator_text, ["http.put(\"request\"", "http.put(\"delete\""])
    ensure_expected("VDB bridge", member_text, ["\"schedule_job\".equals(member)", "\"execute_script\".equals(member)", "\"index_advisor_policy\".equals(member)"])
    ensure_expected("Collection members", member_text, ["\"keys\".equals(member)", "member.equals(\"swap\")", "\"symmetric_difference\".equals(member)"])
    ensure_expected("String methods", string_text, ["case \"split\":", "case \"title\":", "case \"startswith\":", "case \"message\":"])

    base["version"] = date.today().isoformat()
    base["schemaVersion"] = "3.0"
    base["summary"] = (
        "Implementation-derived canonical syntax, runtime, module, VDB, repair, and portal-operation reference "
        "for Versa as executed by verun/vi and used by Verse agents when generating, repairing, opening, and running VI and VDB work."
    )

    base["sources"] = unique_source_entries(
        list(base.get("sources") or [])
        + [
            {"path": "verun/vi/src/main/java/verun/runtime/evaluator/Evaluator.java", "purpose": "Authoritative runtime built-ins and injected module exports"},
            {"path": "verun/vi/src/main/java/verun/runtime/evaluator/MemberAccessEvaluator.java", "purpose": "Authoritative VDB bridge, collection, class, instance, and native member access behavior"},
            {"path": "verun/vi/src/main/java/verun/runtime/evaluator/StringEvaluator.java", "purpose": "Authoritative string member-method surface"},
            {"path": "verun/vi/src/main/java/verun/runtime/modules", "purpose": "Authoritative host-module implementations and helper semantics"},
        ]
    )

    coverage = base.get("coverage") if isinstance(base.get("coverage"), dict) else {}
    coverage["documentedModules"] = ["vdb", "http", "json_xml", "email", "crypto", "jwt", "time", "datetime", "random", "filer", "mediacloud"]
    coverage["runtimeGlobals"] = ["params", "service", "env", "vdb", "auth", "module_config", "module_meta", "unset"]
    style_guidance = list(coverage.get("styleGuidance") or [])
    if "Document Versa directly; do not teach it primarily as a comparison against Python or JavaScript." not in style_guidance:
        style_guidance.append("Document Versa directly; do not teach it primarily as a comparison against Python or JavaScript.")
    coverage["styleGuidance"] = style_guidance
    high_risk = list(coverage.get("knownHighRiskAreas") or [])
    if "Do not reduce VI/VDB workflows to location-only handoffs when the platform can execute the prepared artifact directly." not in high_risk:
        high_risk.append("Do not reduce VI/VDB workflows to location-only handoffs when the platform can execute the prepared artifact directly.")
    coverage["knownHighRiskAreas"] = high_risk
    base["coverage"] = coverage

    highlighting = base.get("highlighting") if isinstance(base.get("highlighting"), dict) else {}
    builtins = list(highlighting.get("builtins") or [])
    for item in ["AsFloat", "json", "xml", "set"]:
        if item not in builtins:
            builtins.append(item)
    highlighting["builtins"] = builtins
    base["highlighting"] = highlighting

    agent_usage = base.get("agentUsage") if isinstance(base.get("agentUsage"), dict) else {}
    priority_rules = list(agent_usage.get("priorityRules") or [])
    if "Treat the method inventories and runtime-derived sections in this reference as implementation-backed, not merely illustrative." not in priority_rules:
        priority_rules.append("Treat the method inventories and runtime-derived sections in this reference as implementation-backed, not merely illustrative.")
    if "When a prepared VI or VDB artifact is executable, prefer direct execution-oriented guidance over workspace-handoff-only guidance." not in priority_rules:
        priority_rules.append("When a prepared VI or VDB artifact is executable, prefer direct execution-oriented guidance over workspace-handoff-only guidance.")
    agent_usage["priorityRules"] = priority_rules
    generation_checklist = list(agent_usage.get("generationChecklist") or [])
    if "Use executeLabel=Run for VI drafts and executeLabel=Run Query for VDB drafts unless the user explicitly asked for a load-only action." not in generation_checklist:
        generation_checklist.append("Use executeLabel=Run for VI drafts and executeLabel=Run Query for VDB drafts unless the user explicitly asked for a load-only action.")
    agent_usage["generationChecklist"] = generation_checklist
    base["agentUsage"] = agent_usage

    retrieval = base.get("retrieval") if isinstance(base.get("retrieval"), dict) else {}
    construct_rules = list(retrieval.get("constructRules") or [])
    construct_rules.append(
        {
            "name": "portal-execution-and-agent-operations",
            "matchAny": [
                "vi portal",
                "vdb portal",
                "run query",
                "save and run",
                "location change",
                "change location",
                "verse agent",
                "run",
            ],
            "sectionIds": ["agent-and-portal-operation-reference"],
        }
    )
    retrieval["constructRules"] = construct_rules
    base["retrieval"] = retrieval

    sections = list(base.get("sections") or [])
    for section in build_sections():
        replace_or_append_section(sections, section)
    quickstart = get_section(sections, "quickstart")
    if isinstance(quickstart, dict):
        rules = list(quickstart.get("rules") or [])
        extra_rule = "Core modules such as vdb, http, json_xml, crypto, jwt, time, datetime, random, email, and filer are only injected when imported at the top of the file."
        if extra_rule not in rules:
            rules.append(extra_rule)
        quickstart["rules"] = rules
    imports_section = get_section(sections, "imports-modules-and-builtins")
    if isinstance(imports_section, dict):
        rules = list(imports_section.get("rules") or [])
        missing_import_rule = "If you call module namespaces such as vdb.*, http.*, json_xml.*, crypto.*, jwt.*, time.*, datetime.*, random.*, email.*, or filer.* without importing the module first, the runtime raises Undefined variable for that module name."
        if missing_import_rule not in rules:
            rules.append(missing_import_rule)
        invalid_examples = list(imports_section.get("invalidExamples") or [])
        missing_import_example = {
            "title": "Using a module namespace without importing it",
            "code": [
                "let result = vdb.find(\"repairs\", {status: \"queued\"}, 5);"
            ],
            "notes": [
                "Add vdb import *; or import vdb; at the top of the file before executable code."
            ],
        }
        if not any(str(item.get("title") or "") == missing_import_example["title"] for item in invalid_examples if isinstance(item, dict)):
            invalid_examples.append(missing_import_example)
        imports_section["rules"] = rules
        imports_section["invalidExamples"] = invalid_examples
    base["sections"] = sections
    return base


def deep_copy_json(value):
    return json.loads(json.dumps(value))


def replace_reference_text(value, replacements: dict[str, str]):
    """Normalize retained prose when generated references are rebuilt."""
    if isinstance(value, str):
        result = value
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result
    if isinstance(value, list):
        return [replace_reference_text(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: replace_reference_text(item, replacements) for key, item in value.items()}
    return value


def classify_reference_section(section_id: str) -> tuple[list[str], str]:
    shared_ids = {
        "vdb-bridge-global-reference",
        "vdb-collection-and-model-reference",
        "agent-and-portal-operation-reference",
    }
    if section_id in shared_ids:
        return ["shared", "versa", "vdb"], "shared"
    return ["versa"], "versa"


def build_vdb_sections() -> list[dict]:
    return [
        {
            "id": "vdb-runtime-surfaces-and-transport",
            "title": "VDB Runtime Surfaces and Transport Modes",
            "summary": "Canonical overview of how VDB is reached from the console, localhost HTTP, Unix sockets, and platform tooling, including the default port and transport-specific expectations.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "transport", "runtime", "http", "socket"],
            "constructs": [
                "./scripts/convo.sh",
                "./scripts/serve.sh",
                "./scripts/socket.sh",
                "POST /auth",
                "POST /vql",
                "GET /help",
            ],
            "queryHints": [
                "vdb http server",
                "vdb unix socket",
                "vdb localhost port",
                "vdb /auth",
                "vdb /vql",
            ],
            "syntaxPatterns": [
                "cd verun/vdb && ./scripts/convo.sh",
                "cd verun/vdb && ./scripts/serve.sh",
                "curl -X POST http://127.0.0.1:1957/auth --user username:password",
            ],
            "rules": [
                "Use the console when you want an interactive local session without transport headers.",
                "Use POST /auth first for HTTP access, then carry the returned X-Session-Id into later POST /vql and GET /help calls.",
                "The default HTTP port is 1957.",
                "Unix sockets are the local same-host transport on Unix-like systems; the transport guide notes that Windows should prefer named pipes instead of raw Unix sockets.",
                "Treat localhost HTTP, Unix socket, and portal tooling as transport variants over the same VQL command model rather than different query languages.",
            ],
            "tables": [
                {
                    "title": "Primary VDB runtime surfaces",
                    "columns": ["Surface", "Entry point", "Use when", "Notes"],
                    "rows": [
                        ["Console", "./scripts/convo.sh", "You want an interactive shell on the local machine.", "No HTTP headers or session-copy steps are needed inside the console flow."],
                        ["HTTP server", "./scripts/serve.sh", "A local app, curl, or UI needs localhost HTTP access.", "Exposes /auth, /vql, and /help on port 1957 by default."],
                        ["Unix socket server", "./scripts/socket.sh", "Local tooling should avoid TCP and stay on a host-local IPC channel.", "Useful for same-machine automation on Unix-like systems."],
                        ["Portal/tooling", "Liwiro VDB surfaces", "The platform is issuing VQL or opening prepared queries for the user.", "Still uses the same VDB command model underneath."],
                    ],
                },
                {
                    "title": "HTTP endpoints",
                    "columns": ["Endpoint", "Method", "Auth expectation", "Purpose"],
                    "rows": [
                        ["/auth", "POST", "HTTP Basic auth", "Authenticate and obtain a sessionId."],
                        ["/vql", "POST", "X-Session-Id header", "Execute one VQL request or a request batch."],
                        ["/help", "GET", "X-Session-Id header", "Return help content filtered by RBAC and current scope."],
                    ],
                },
                {
                    "title": "Transport selection guidance",
                    "columns": ["Environment", "Preferred transport", "Why"],
                    "rows": [
                        ["Interactive local debugging", "Console", "Fastest feedback and direct runtime prompts."],
                        ["Local app or UI integration", "HTTP localhost", "Simplest transport for browser-like and service tooling."],
                        ["Unix-like automation on one host", "Unix socket", "Avoids a localhost TCP hop and keeps the channel host-local."],
                        ["Windows host-local automation", "Named pipe", "The transport guide documents named pipes as the Windows-local IPC path."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Authenticate then execute over HTTP",
                    "code": [
                        "curl -X POST http://127.0.0.1:1957/auth --user username:password",
                        "",
                        "curl -X POST http://127.0.0.1:1957/vql \\",
                        "  -H 'X-Session-Id: <SESSION_ID>' \\",
                        "  -H 'Content-Type: application/json' \\",
                        "  -H 'Content-Type: text/plain' --data 'echo \"hello\"'",
                    ],
                    "notes": [
                        "The second call reuses the session returned by /auth.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-auth-sessions-and-context",
            "title": "VDB Authentication, Sessions, and Context",
            "summary": "How users authenticate, how session state is created and refreshed, and how current domain and database context travel with later requests.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "auth", "sessions", "context", "whoami"],
            "constructs": [
                "POST /auth",
                "X-Session-Id",
                "context",
                "whoami",
                "use domain \"...\" db \"...\"",
            ],
            "queryHints": [
                "vdb session timeout",
                "vdb context command",
                "vdb whoami",
                "vdb active domain",
                "vdb auth flow",
            ],
            "syntaxPatterns": [
                "context",
                "whoami",
                "use domain \"engineering\" db \"main\"",
            ],
            "rules": [
                "HTTP authentication is a two-step flow: POST /auth with Basic credentials, then reuse the returned sessionId in X-Session-Id.",
                "Session state carries the current domain and database, and VQLProcessor updates that session context when use/domain changes occur.",
                "SessionManager validates and refreshes active sessions; the runtime timeout is 30 minutes of inactivity.",
                "Use context and whoami as diagnostics before assuming a query bug when scope-sensitive commands behave unexpectedly.",
                "Re-authenticate to obtain a fresh sessionId when the server reports Invalid or expired session.",
            ],
            "tables": [
                {
                    "title": "Authentication and session lifecycle",
                    "columns": ["Step", "Input", "Output", "Notes"],
                    "rows": [
                        ["Authenticate", "POST /auth with Basic credentials", "sessionId", "Required before HTTP /vql or /help calls."],
                        ["Use session", "X-Session-Id: <sessionId>", "Scoped request execution", "The same session holds user, domain, and db context."],
                        ["Refresh", "Any validated request", "Updated last-access time", "Active sessions are refreshed on validation."],
                        ["Expire", "No activity for 30 minutes", "401 invalid/expired session", "Re-authenticate and retry with the new sessionId."],
                    ],
                },
                {
                    "title": "Context-oriented commands",
                    "columns": ["Command", "Primary purpose", "What it returns"],
                    "rows": [
                        ["context", "Inspect current runtime scope", "Active domain, active db, and session/runtime context."],
                        ["whoami", "Inspect authenticated identity", "Current user and role/scope context."],
                        ["use domain \"...\" db \"...\"", "Switch active scope", "Updated context bound to the session."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Check current scope before a privileged command",
                    "code": [
                        "whoami",
                        "context",
                        "use domain \"liwiro\" db \"main\"",
                        "context",
                    ],
                    "notes": [
                        "This sequence confirms identity, current scope, and post-switch scope using only low-risk diagnostics.",
                    ],
                }
            ],
            "invalidExamples": [
                {
                    "title": "Calling /vql without a session header",
                    "code": [
                        "curl -X POST http://127.0.0.1:1957/vql -H 'Content-Type: text/plain' --data 'read domains'",
                    ],
                    "notes": [
                        "Authenticate first and send X-Session-Id with the returned sessionId.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-domain-database-and-collection-lifecycle",
            "title": "VDB Domain, Database, and Collection Lifecycle",
            "summary": "How VDB creates and selects domains and databases, inspects available scopes, manages models, and creates or drops collections.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "domain", "database", "collection", "model"],
            "constructs": [
                "create domain \"engineering\"",
                "create domain \"engineering\" db \"main\"",
                "use domain \"engineering\" db \"main\"",
                "create collection \"users\" schema {\"name\":{\"type\":\"string\"}}",
                "read model model \"users\"",
                "status domain \"engineering\"",
            ],
            "queryHints": [
                "vdb define domain",
                "vdb define db",
                "vdb list collections",
                "vdb model get",
                "vdb drop collection",
                "vdb domain status",
            ],
            "syntaxPatterns": [
                "read domains",
                "read dbs",
                "create collection \"users\" schema {\"name\":{\"type\":\"string\"},\"age\":{\"type\":\"int\"}}",
                "drop collection \"users\"",
                "suspend domain \"engineering\"",
                "resume domain \"engineering\"",
            ],
            "rules": [
                "Use define to create scope metadata and use to activate it for later commands.",
                "list is the low-risk way to discover domains, databases, collections, and models before mutation.",
                "Model metadata and collection data are related but not identical: model operations manage schema metadata while collection commands affect the data surface.",
                "drop commands are destructive and scope-sensitive.",
                "domain_status is a read-only lifecycle check; domain_suspend and domain_resume are ownership-sensitive mutations and suspended domains cannot be selected by ordinary users.",
                "Prefer explicit domain/db activation before model, CRUD, export, or TUMI work so permission checks resolve against the intended scope.",
            ],
            "tables": [
                {
                    "title": "Domain and database commands",
                    "columns": ["Command", "Purpose", "Notes"],
                    "rows": [
                        ["create domain \"engineering\"", "Create a domain", "Creates a domain metadata root."],
                        ["create domain \"engineering\" db \"main\"", "Create a domain and db", "Useful during initial scope setup."],
                        ["use domain \"engineering\" db \"main\"", "Switch active scope", "Stores the chosen domain/db in the current session context."],
                        ["read domains", "List domains", "Safe discovery command."],
                        ["read dbs", "List databases in current domain", "Requires current domain context."],
                        ["drop domain \"engineering\"", "Drop a domain", "Destructive; role and ownership sensitive."],
                        ["drop db \"main\"", "Drop a database", "Destructive; applies in the current domain."],
                    ],
                },
                {
                    "title": "Collection and model commands",
                    "columns": ["Command", "Purpose", "Notes"],
                    "rows": [
                        ["create collection \"users\" schema {\"name\":{\"type\":\"string\"},\"age\":{\"type\":\"int\"}}", "Create a collection and its field metadata", "The create family defines the model shape in current scope."],
                        ["read collections", "List collections", "Reads the current db's collection inventory."],
                        ["read models", "List models", "Reads model metadata names."],
                        ["read model model \"users\"", "Inspect model metadata", "Useful before update, projection, or schema repair."],
                        ["delete model model \"users\"", "Delete model metadata", "Metadata-focused deletion, distinct from dropping the whole collection."],
                        ["drop collection \"users\"", "Drop collection data and metadata surface", "Destructive collection removal."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Create and inspect a scoped collection",
                    "code": [
                        "create domain \"engineering\" db \"main\"",
                        "use domain \"engineering\" db \"main\"",
                        "create collection \"users\" schema {\"name\":{\"type\":\"string\"},\"age\":{\"type\":\"int\"}}",
                        "read model model \"users\"",
                        "read collections",
                    ],
                    "notes": [
                        "The sequence creates scope, activates it, defines a collection, and verifies the result using non-destructive reads.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-crud-query-and-projection-reference",
            "title": "VDB CRUD, Query Operators, and Projection",
            "summary": "Canonical request shapes for create/read/update/delete, the currently documented comparison operators, and the read-time args used for limiting and projection-like access patterns.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "crud", "query", "projection", "operators"],
            "constructs": [
                "create in users = { name: \"John\", age: 30 };",
                "read collection users where age > 25 limit 10;",
                "update collection users where name == \"John\" { age = 31; };",
                "delete from users where active == false;",
            ],
            "queryHints": [
                "vdb read query",
                "vdb update payload shape",
                "vdb delete payload shape",
                "vdb projection",
                "vdb query operators",
            ],
            "syntaxPatterns": [
                "read collection users where age >= 18 limit 5;",
                "update collection users where name == \"John\" { age = 31; };",
                "delete from users where active == false;",
            ],
            "rules": [
                "Every VDB command is a flat JSON object with an action field; insert uses document, find uses where, and update uses set/inc/unset.",
                "Do not emit legacy nested operation envelopes such as {read:{...}}, {update:{...}}, or {delete:{...}}.",
                "The documented comparison operators are $eq, $ne, $lt, $gt, $lte, $gte, $in, and $nin.",
                "args.limit is the explicitly documented limit control in the core VQL reference.",
                "The runtime accepts readable statements; JSON command envelopes are invalid.",
            ],
            "tables": [
                {
                    "title": "CRUD request families",
                    "columns": ["Family", "Canonical shape", "Notes"],
                    "rows": [
                        ["insert", "create in users = { name: \"John\", age: 30 };", "Insert one document."],
                        ["find", "read collection users where age > 25 limit 10;", "Find matching documents."],
                        ["update", "update collection users where name == \"John\" { age = 31; };", "Update matching documents."],
                        ["delete", "delete from users where active == false;", "Delete matching documents."],
                    ],
                },
                {
                    "title": "Documented query operators",
                    "columns": ["Operator", "Meaning"],
                    "rows": [
                        ["$eq", "Equals"],
                        ["$ne", "Not equal"],
                        ["$lt", "Less than"],
                        ["$gt", "Greater than"],
                        ["$lte", "Less than or equal"],
                        ["$gte", "Greater than or equal"],
                        ["$in", "Contained in a provided list"],
                        ["$nin", "Not contained in a provided list"],
                    ],
                },
                {
                    "title": "Read-time shaping hints from current docs/runtime",
                    "columns": ["Input", "Where it appears", "Notes"],
                    "rows": [
                        ["args.limit", "Core VQL reference", "Explicitly documented limit control."],
                        ["args.projection", "Runtime implementation", "Projection handling exists in VQLProcessor and Collection helpers."],
                        ["sort/projection examples", "Usage guide", "Treat as advanced guidance and verify against the target runtime contract before relying on them."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Read a bounded result set with a comparison operator",
                    "code": [
                        "read collection users where age >= 18 limit 5;",
                    ],
                    "notes": [
                        "This keeps to the explicit request family and the documented args.limit control.",
                    ],
                }
            ],
            "invalidExamples": [
                {
                    "title": "Assuming update uses the read payload shape",
                    "code": [
                        "update collection users where name == \"John\" { age = 31; };",
                    ],
                    "notes": [
                        "Use a readable update statement with where and set/inc/unset options.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-script-transaction-and-export-reference",
            "title": "VDB Scripts, Transactions, Export, and Batch Requests",
            "summary": "Stored script commands, transaction boundaries, export packaging rules, and the array-based batch request form supported by VDB.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "scripts", "transactions", "export", "batch"],
            "constructs": [
                "create script name \"greet\" service \"utils\" code \"print('Hello');\"",
                "begin transaction",
                "export domains [\"default\"] out_dir \"/tmp/vdb-exports\"",
                "echo value \"start\";\nread domains;\ncontext",
            ],
            "queryHints": [
                "vdb stored script",
                "vdb transaction begin",
                "vdb export zip",
                "vdb batch request",
            ],
            "syntaxPatterns": [
                "read script name \"greet\"",
                "commit transaction",
                "export domains \"*\" package \"all-domains\" out_dir \"/tmp/vdb-exports\"",
            ],
            "rules": [
                "Stored scripts are first-class VDB records and are distinct from the Versa-side vdb bridge helpers that call into them.",
                "Transactions are explicit begin/commit/abort commands; keep the lifecycle visible in the request stream instead of assuming implicit batching.",
                "Export requires out_dir and produces packaged zip output.",
                "Export permissions are role- and scope-sensitive.",
                "A batch request is either a JSON array of normal flat-action objects or a {commands:[...]} wrapper; it is not relaxed scripting syntax.",
            ],
            "tables": [
                {
                    "title": "Stored script commands",
                    "columns": ["Command", "Purpose", "Notes"],
                    "rows": [
                        ["create script name \"greet\" service \"utils\" code \"print('Hello');\"", "Create a stored script", "Stores code plus script metadata."],
                        ["read script name \"greet\"", "Read stored script metadata/code", "Safe inspection step before execution."],
                        ["run script name \"greet\" params {\"username\":\"john\"}", "Execute a stored script", "Pass request parameters through params."],
                        ["delete script name \"greet\"", "Delete a stored script", "Destructive operation."],
                    ],
                },
                {
                    "title": "Transactions, export, and batching",
                    "columns": ["Feature", "Canonical form", "Notes"],
                    "rows": [
                        ["Begin transaction", "begin transaction", "Start a transaction boundary."],
                        ["Commit transaction", "commit transaction", "Commit the active transaction."],
                        ["Abort transaction", "abort transaction", "Abort the active transaction."],
                        ["Export", "export domains [\"default\"] out_dir \"/tmp/vdb-exports\"", "out_dir is required; package is optional."],
                        ["Batch request", "echo value \"start\";\nread domains;\ncontext", "Semicolon-separated readable statements."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Create and execute a stored script",
                    "code": [
                        "create script name \"greet\" service \"utils\" code \"print(\\\"Hello\\\");\"",
                        "run script name \"greet\" params {\"username\":\"john\"}",
                    ],
                    "notes": [
                        "Read the script first when debugging permissions, code drift, or stale metadata.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-help-echo-context-and-response-shapes",
            "title": "VDB Help, Echo, Context, and Response Shapes",
            "summary": "Low-risk command families used to inspect runtime state and the common success/error envelope that most VDB responses share.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "help", "echo", "context", "response"],
            "constructs": [
                "echo value \"hello\"",
                "help topic \"domains\"",
                "context",
                "whoami",
            ],
            "queryHints": [
                "vdb help command",
                "vdb response shape",
                "vdb echo",
                "vdb whoami response",
            ],
            "syntaxPatterns": [
                "help topic \"collections\"",
                "help topic \"tumi\"",
                "echo value \"hello\"",
            ],
            "rules": [
                "Start with echo, help, whoami, or context when you want to validate transport and auth before attempting mutation.",
                "Help output is filtered by RBAC and current scope, especially around security and TUMI content.",
                "Common response fields are status, message, and data.",
                "Error responses usually return status: error plus a human-readable message.",
            ],
            "tables": [
                {
                    "title": "Diagnostic command families",
                    "columns": ["Command", "Purpose", "Typical output"],
                    "rows": [
                        ["echo value \"hello\"", "Round-trip transport check", "Echoed value."],
                        ["help topic \"domains\"", "Discover command help", "Topic-specific help content."],
                        ["context", "Inspect active scope", "Session/runtime context including domain/db."],
                        ["whoami", "Inspect identity", "Current user and scope context."],
                    ],
                },
                {
                    "title": "Common response fields",
                    "columns": ["Field", "Meaning"],
                    "rows": [
                        ["status", "Overall success or error state."],
                        ["message", "Human-readable explanation of the result."],
                        ["data", "Operation payload or returned rows/metadata."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Diagnose auth and scope before mutation",
                    "code": [
                        "echo value \"transport ok\"",
                        "whoami",
                        "context",
                        "help topic \"collections\"",
                    ],
                    "notes": [
                        "This sequence is safe to run while debugging connectivity, auth, or scope issues.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-tumi-rbac-and-security-reference",
            "title": "VDB TUMI, RBAC, and Security Reference",
            "summary": "Canonical TUMI command families, role and ownership expectations, and the security-sensitive rules that gate user, role, and permission work.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "tumi", "rbac", "security", "permissions"],
            "constructs": [
                "create user username \"liwiro\" email \"liwiro@local.com\" password \"...\" role \"APP\"",
                "grant username \"john\" domain \"hr\" db \"employee_data\" permissions [\"READ\",\"WRITE\"]",
                "read roles",
                "revoke username \"john\" domain \"hr\" db \"employee_data\" collection \"payroll\" permissions [\"READ\"]",
            ],
            "queryHints": [
                "vdb tumi create user",
                "vdb tumi grant",
                "vdb roles",
                "vdb domain ownership",
            ],
            "syntaxPatterns": [
                "create role \"REPORT_VIEWER\" scope {\"domain\":\"hr\",\"db\":\"employee_data\"} permissions [\"READ\"]",
                "grant username \"john\" domain \"hr\" db \"employee_data\" permissions [\"READ\",\"WRITE\"]",
            ],
            "rules": [
                "SUPER_ADMIN is required for user and role creation/deletion in the canonical docs.",
                "System roles are read-only.",
                "Grants and revokes are scope-sensitive and can target db-level or collection-level permissions.",
                "Domain owners can manage delegated access inside domains they own, but they do not automatically gain every super-admin-only capability.",
                "Treat TUMI as security-sensitive infrastructure, not as a convenience command family for everyday CRUD.",
            ],
            "tables": [
                {
                    "title": "TUMI command families",
                    "columns": ["Family", "Purpose", "Notes"],
                    "rows": [
                        ["create", "Create users or role definitions", "Security-sensitive; user and role creation is super-admin gated in the docs."],
                        ["read", "Inspect a user, role, or permission target", "Low-risk inspection path."],
                        ["update", "Modify TUMI-managed entities", "Still permission-gated."],
                        ["delete", "Delete users or roles", "Security-sensitive and destructive."],
                        ["grant / revoke", "Assign or remove permissions/roles", "Scope-sensitive; may include collection-level targets."],
                        ["list", "List roles, users, or delegated views", "Often the first safe discovery step."],
                        ["transfer", "Transfer domain ownership", "Domain-ownership sensitive operation."],
                    ],
                },
                {
                    "title": "Security and permission highlights",
                    "columns": ["Rule", "Why it matters"],
                    "rows": [
                        ["SUPER_ADMIN for user/role creation and deletion", "Prevents ordinary app or user sessions from provisioning privileged identities."],
                        ["System roles are read-only", "Built-in roles are not edited through ordinary role mutation."],
                        ["Domain ownership matters", "Owned domains unlock delegation within that domain without turning the user into a system super-admin."],
                        ["Collection-level permission targets exist", "Grant/revoke can narrow scope below the db level."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Grant scoped db permissions",
                    "code": [
                        "grant username \"john\" domain \"hr\" db \"employee_data\" permissions [\"READ\",\"WRITE\"]",
                        "read roles",
                    ],
                    "notes": [
                        "List or read commands are the safe follow-up after any grant/revoke change.",
                    ],
                }
            ],
            "invalidExamples": [
                {
                    "title": "Treating TUMI as an unscoped grant API",
                    "code": [
                        "grant username \"john\" permissions [\"READ\"]",
                    ],
                    "notes": [
                        "Provide the required scope such as domain and db, and collection when narrowing further.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-persistence-operations-and-layout",
            "title": "VDB Persistence Layout and Operations",
            "summary": "Where VDB stores durable state, which operational scripts and logs matter in practice, and which files operators inspect when debugging transport or persistence issues.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "operations", "persistence", "logs", "storage"],
            "constructs": [
                "verun/vdb/__data__",
                "verun/vdb/logs",
                "verun/vdb/__data__/sys/users",
                "verun/vdb/__data__/sys/index_advisor",
            ],
            "queryHints": [
                "vdb data directory",
                "vdb user storage",
                "vdb logs",
                "vdb index advisor files",
            ],
            "syntaxPatterns": [
                "cd verun/vdb && ./scripts/serve.sh",
                "cd verun/vdb && ./scripts/socket.sh",
                "VDB_CONSOLE_LOGS=false VDB_HTTP_TRAFFIC_LOGS=false ./scripts/serve.sh",
            ],
            "rules": [
                "The durable runtime tree lives under verun/vdb/__data__ and becomes the source of truth for domains, databases, collections, users, scripts, and operational metadata.",
                "User and permission metadata persist under __data__/sys/users.",
                "Index advisor state persists under __data__/sys/index_advisor.",
                "Operational logs live under verun/vdb/logs and are often the fastest way to separate transport failure from permission failure.",
                "Turn down verbose logging with the documented environment flags when you need quieter runs rather than editing code paths.",
            ],
            "tables": [
                {
                    "title": "Operational layout",
                    "columns": ["Path", "What it stores", "Why it matters"],
                    "rows": [
                        ["verun/vdb/__data__/domains", "Domain/db data and metadata", "Primary durable application data surface."],
                        ["verun/vdb/__data__/scripts", "Stored script payloads", "Source of truth for VDB-native stored scripts."],
                        ["verun/vdb/__data__/sys/users", "Users and permission metadata", "Security and RBAC debugging starts here."],
                        ["verun/vdb/__data__/sys/index_advisor", "Index advisor statistics and recommendations", "Useful for performance-oriented investigations."],
                        ["verun/vdb/logs", "Runtime logs", "Separates transport/auth issues from query-shape or permission issues."],
                    ],
                },
                {
                    "title": "Operational entrypoints and flags",
                    "columns": ["Entrypoint or flag", "Purpose", "Notes"],
                    "rows": [
                        ["./scripts/convo.sh", "Interactive console", "Best for direct local command exploration."],
                        ["./scripts/serve.sh", "HTTP server", "Default localhost transport."],
                        ["./scripts/socket.sh", "Unix socket server", "Local IPC transport for Unix-like hosts."],
                        ["VDB_CONSOLE_LOGS=false", "Reduce console log noise", "Documented in setup notes."],
                        ["VDB_HTTP_TRAFFIC_LOGS=false", "Reduce HTTP traffic logging", "Useful when running the HTTP server in repetitive tests."],
                    ],
                },
            ],
            "validExamples": [
                {
                    "title": "Start a quieter HTTP server for local debugging",
                    "code": [
                        "cd verun/vdb",
                        "VDB_CONSOLE_LOGS=false VDB_HTTP_TRAFFIC_LOGS=false ./scripts/serve.sh",
                    ],
                    "notes": [
                        "This uses the documented runtime flags rather than editing any logging implementation code.",
                    ],
                }
            ],
        },
        {
            "id": "vdb-mistakes-and-repair-reference",
            "title": "VDB Mistakes, Failure Modes, and Repair Workflow",
            "summary": "High-frequency VDB failure patterns and the shortest safe recovery path for each one, covering transport, auth, scope, command syntax, and permission issues.",
            "domains": ["vdb"],
            "group": "vdb",
            "tags": ["vdb", "troubleshooting", "mistakes", "repair"],
            "constructs": [
                "Invalid or expired session",
                "No active domain context",
                "No active database context",
                "Permission denied",
                "readable VDB syntax",
            ],
            "queryHints": [
                "vdb invalid session",
                "vdb no active domain context",
                "vdb permission denied",
                "vdb readable command syntax",
            ],
            "syntaxPatterns": [
                "context",
                "whoami",
                "read domains",
                "use domain \"liwiro\" db \"main\"",
            ],
            "rules": [
                "Debug transport first, then auth, then scope, then permissions, and only then the query body itself.",
                "A well-formed request can still fail when the authenticated user lacks the required role or scope.",
                "Use readable VDB statements; JSON is reserved for data literals such as filters and documents.",
                "Re-check context after any use/define step before assuming later commands are reading the same domain/db you intended.",
            ],
            "errors": [
                {
                    "errorContains": "Invalid or expired session",
                    "meaning": "The HTTP request used a missing, stale, or timed-out sessionId.",
                    "fix": [
                        "POST /auth again with valid credentials.",
                        "Retry the request with the new X-Session-Id header.",
                    ],
                },
                {
                    "errorContains": "No active domain context / No active database context",
                    "meaning": "A scope-sensitive command ran before the session selected a usable domain or database.",
                    "fix": [
                        "Run a context command to confirm the current scope.",
                        "Issue a use command with the intended domain and db, then retry.",
                    ],
                },
                {
                    "errorContains": "Permission denied",
                    "meaning": "The authenticated identity lacks the required role, domain ownership, or scoped permission for the requested command.",
                    "fix": [
                        "Run whoami and context to verify the active user and scope.",
                        "Use TUMI or a higher-privilege identity to grant the required permission when appropriate.",
                    ],
                },
                {
                    "errorContains": "Unreadable or malformed command",
                    "meaning": "The request body did not use readable VDB command syntax.",
                    "fix": [
                        "Check the command against the examples returned by help.",
                        "Use a verb and target followed by named options, such as read collection users limit 10.",
                    ],
                },
            ],
            "invalidExamples": [
                {
                    "title": "Sending an old JSON command envelope",
                    "code": [
                        "{action: find, collection: users, where: {age: {$gt: 25}}}",
                    ],
                    "notes": [
                        "Rewrite the request as a readable statement; keep JSON only for data literals.",
                    ],
                }
            ],
            "validExamples": [
                {
                    "title": "Minimal repair pass before retrying a failed request",
                    "code": [
                        "echo value \"transport ok\"",
                        "whoami",
                        "context",
                        "use domain \"liwiro\" db \"main\"",
                        "read collection users where age > 25 limit 5;",
                    ],
                    "notes": [
                        "This sequence narrows transport, auth, scope, and query-shape issues in a deterministic order.",
                    ],
                }
            ],
        },
    ]


def replace_or_append_construct_rule(rules: list[dict], rule: dict) -> None:
    name = str(rule.get("name") or "").strip()
    for index, existing in enumerate(rules):
        if str(existing.get("name") or "").strip() == name:
            rules[index] = rule
            return
    rules.append(rule)


def build_vvr_payload(versa_payload: dict) -> dict:
    payload = deep_copy_json(versa_payload)
    payload["title"] = "Verse-Verun Reference"
    payload["schemaVersion"] = "4.0"
    payload["canonicalPath"] = "verun/vi/verse-verun-reference/reference.json"
    payload["htmlPath"] = "verun/vi/verse-verun-reference/index.html"
    payload["summary"] = (
        "Combined implementation-backed reference for Versa, VDB, and their shared Verse/Liwiro runtime flows. "
        "This bundle expands the canonical Versa material into a broader Verse-Verun reference with VDB coverage "
        "that is structured, retrievable, and example-driven at the same level as the Versa half."
    )

    payload["sources"] = unique_source_entries(
        list(payload.get("sources") or [])
        + [
            {"path": "docs/verun/vdb/README.md", "purpose": "High-level VDB overview and runtime entrypoints"},
            {"path": "docs/verun/vdb/setup-and-operations.md", "purpose": "Operational startup, auth, transport, and troubleshooting guidance"},
            {"path": "docs/verun/vdb/vql-reference.md", "purpose": "Canonical VQL request families, operators, and core examples"},
            {"path": "docs/verun/vdb/usage-guide.md", "purpose": "Operator workflows and advanced usage notes that complement the canonical request families"},
            {"path": "docs/verun/vdb/auth-and-rbac-notes.md", "purpose": "Authentication and authorization notes for roles, permissions, and durable user storage"},
            {"path": "docs/verun/vdb/tumi-rbac.md", "purpose": "TUMI and RBAC delegation rules"},
            {"path": "docs/verun/vdb/vdb-interface-transport-guide.html", "purpose": "Transport-selection guidance across HTTP, Unix sockets, and named pipes"},
            {"path": "verun/vdb/src/main/java/verun/vdb/VDBRequestDispatcher.java", "purpose": "Authoritative HTTP auth, help, and session-header behavior"},
            {"path": "verun/vdb/src/main/java/verun/vdb/VQLProcessor.java", "purpose": "Authoritative VQL command dispatch, scope handling, and projection support"},
            {"path": "verun/vdb/src/main/java/verun/vdb/SessionManager.java", "purpose": "Authoritative session timeout and refresh behavior"},
            {"path": "verun/vdb/src/main/java/verun/vdb/Tumi.java", "purpose": "Authoritative TUMI command families and permission checks"},
            {"path": "verun/vdb/src/main/resources/help.json", "purpose": "Bundled help topics surfaced by VDB help routes"},
            {"path": "verun/vdb/src/main/resources/queries", "purpose": "Bundled request-family examples used by the VDB runtime"},
        ]
    )

    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    coverage["referenceFamilies"] = [
        "Versa language and parser rules",
        "Versa runtime globals and member methods",
        "Versa injected modules",
        "Versa <-> VDB bridge",
        "VDB transport, auth, and context",
        "VDB VQL command families",
        "VDB scripts, export, and operations",
        "VDB TUMI/RBAC and security",
    ]
    coverage["documentedSurfaces"] = ["versa", "vdb", "shared"]
    coverage["vdbCommandFamilies"] = [
        "define",
        "use",
        "list",
        "create",
        "read",
        "update",
        "delete",
        "drop",
        "model",
        "script",
        "transaction",
        "export",
        "tumi",
        "context",
        "whoami",
        "help",
        "echo",
    ]
    coverage["transportSurfaces"] = ["console", "http", "unix socket", "named pipe guidance", "portal/tooling"]
    payload["coverage"] = coverage

    agent_usage = payload.get("agentUsage") if isinstance(payload.get("agentUsage"), dict) else {}
    priority_rules = list(agent_usage.get("priorityRules") or [])
    additions = [
        "Use VDB-native sections for HTTP, VQL, TUMI, export, and transport questions instead of inferring them from the Versa vdb bridge alone.",
        "Treat the shared sections as the hand-off layer between Versa authoring and VDB execution rather than duplicating the same guidance in both domains.",
        "When VDB docs and runtime implementation differ, prefer the implementation-backed sections in this bundle and note the mismatch explicitly.",
    ]
    for item in additions:
        if item not in priority_rules:
            priority_rules.append(item)
    agent_usage["priorityRules"] = priority_rules

    generation_checklist = list(agent_usage.get("generationChecklist") or [])
    extra_checklist = "For VDB examples, use readable statements and reserve JSON for data literals such as filters, documents, and pipelines."
    if extra_checklist not in generation_checklist:
        generation_checklist.append(extra_checklist)
    agent_usage["generationChecklist"] = generation_checklist

    missing_policy = list(agent_usage.get("missingInfoPolicy") or [])
    vdb_policy = "If the combined reference does not document a VDB command family or payload field, do not invent it; fall back to a simpler documented request or stop."
    if vdb_policy not in missing_policy:
        missing_policy.append(vdb_policy)
    agent_usage["missingInfoPolicy"] = missing_policy
    payload["agentUsage"] = agent_usage

    retrieval = payload.get("retrieval") if isinstance(payload.get("retrieval"), dict) else {}
    required = list(retrieval.get("requiredSectionIds") or [])
    for section_id in [
        "vdb-runtime-surfaces-and-transport",
        "vdb-auth-sessions-and-context",
        "vdb-crud-query-and-projection-reference",
    ]:
        if section_id not in required:
            required.append(section_id)
    retrieval["requiredSectionIds"] = required

    defaults = list(retrieval.get("defaultSectionIds") or [])
    for section_id in [
        "vdb-domain-database-and-collection-lifecycle",
        "vdb-help-echo-context-and-response-shapes",
        "vdb-tumi-rbac-and-security-reference",
    ]:
        if section_id not in defaults:
            defaults.append(section_id)
    retrieval["defaultSectionIds"] = defaults

    construct_rules = list(retrieval.get("constructRules") or [])
    for rule in [
        {
            "name": "vdb-http-auth-and-session-flow",
            "matchAny": ["x-session-id", "/auth", "/vql", "sessionId", "invalid or expired session", "whoami", "context"],
            "sectionIds": ["vdb-runtime-surfaces-and-transport", "vdb-auth-sessions-and-context"],
        },
        {
            "name": "vdb-domain-db-model-and-collection-setup",
            "matchAny": ["define domain", "define db", "use domain", "list collections", "model", "drop collection", "list domains", "list dbs"],
            "sectionIds": ["vdb-domain-database-and-collection-lifecycle"],
        },
        {
            "name": "vdb-crud-and-query-shapes",
            "matchAny": ["read", "update", "delete", "$gt", "$gte", "$in", "projection", "args.limit", "strict json", "batch request"],
            "sectionIds": ["vdb-crud-query-and-projection-reference", "vdb-mistakes-and-repair-reference"],
        },
        {
            "name": "vdb-scripts-export-and-transactions",
            "matchAny": ["script execute", "stored script", "transaction begin", "transaction commit", "export", "batch"],
            "sectionIds": ["vdb-script-transaction-and-export-reference"],
        },
        {
            "name": "vdb-rbac-and-tumi",
            "matchAny": ["tumi", "grant", "revoke", "role", "domain ownership", "permission denied", "super_admin"],
            "sectionIds": ["vdb-tumi-rbac-and-security-reference", "vdb-mistakes-and-repair-reference"],
        },
        {
            "name": "vdb-operations-and-storage",
            "matchAny": ["__data__", "sessions.log", "index_advisor", "socket.sh", "serve.sh", "convo.sh", "vdb logs"],
            "sectionIds": ["vdb-persistence-operations-and-layout", "vdb-runtime-surfaces-and-transport"],
        },
    ]:
        replace_or_append_construct_rule(construct_rules, rule)
    retrieval["constructRules"] = construct_rules
    payload["retrieval"] = retrieval

    payload["sectionGroups"] = [
        {
            "id": "versa",
            "title": "Versa / VI",
            "description": "Language syntax, runtime, modules, repair workflow, and parser-grounded authoring rules.",
        },
        {
            "id": "vdb",
            "title": "VDB",
            "description": "Transport, auth, VQL, operations, export, RBAC, and persistent data-layer behavior.",
        },
        {
            "id": "shared",
            "title": "Shared",
            "description": "Shared runtime and bridge behavior where Versa, VDB, Verse, and Liwiro overlap.",
        },
    ]

    sections: list[dict] = []
    for section in list(payload.get("sections") or []):
        section_id = str(section.get("id") or "").strip()
        domains, group = classify_reference_section(section_id)
        enriched = deep_copy_json(section)
        enriched["domains"] = domains
        enriched["group"] = group
        sections.append(enriched)
    sections.extend(build_vdb_sections())
    payload["sections"] = sections
    return payload


def main() -> None:
    payload = augment_reference()
    REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    VVR_PATH.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    VVR_PATH.write_text(json.dumps(build_vvr_payload(payload), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
