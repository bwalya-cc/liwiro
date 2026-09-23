# MIT License and Acceptance

Last updated: 2026-03-13

Verun + Liwiro now uses a simple MIT license flow.

## Runtime behavior

- `/license` returns the MIT disclosure payload.
- `/health` returns a lightweight runtime health payload.
## Acceptance behavior

- VDB startup requires a one-time MIT acceptance marker.
- Interactive startup prompts use `Accept MIT license? [y/N]:`.
- Only `y` or `Y` records acceptance.
- The acceptance marker is stored at `verun/vdb/__data__/sys/mit-license-acceptance.bson` by default.

## Notes

- The repository is MIT-licensed.
- Third-party dependencies still keep their own licenses.
- The MIT acceptance prompt does not enable any commercial or telemetry mode.
