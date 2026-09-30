# Endpoint Types

## CRUD

CRUD endpoints operate on one linked model. Select a CRUD operation and keep the linked model name valid.

## Custom VDB command

Custom endpoints require readable VDB command text. Do not provide a JSON command envelope or SQL.

## Versa script

Script endpoints require complete Versa source. Imports must appear before executable code. Use documented Versa syntax and return a response object. Save the endpoint configuration, then test the restarted service.
