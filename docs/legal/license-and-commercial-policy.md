# Verun + Liwiro License Policy

Last updated: 2026-03-10

Copyright owner: **Bwalya Cameron Chishimba**

SPDX license expression:

- `MIT`

## Repository License

This repository is released under the MIT License.

MIT allows use, modification, distribution, sublicensing, and sale of the software, provided that the copyright notice and MIT license text are kept with substantial portions of the software.

## Dependency-Licensing Notes

The repository license applies to the source code in this repo. Third-party dependencies remain under their own licenses.

Based on the current manifests:

- `liwiro/backend/requirements.txt` declares common permissive Python dependencies
- `verun/vdb/pom.xml` and `verun/vi/pom.xml` declare permissive Java dependencies plus test-scoped JUnit
- `liwiro/frontend/package-lock.json` includes mostly MIT/Apache/BSD/ISC packages, plus optional `sharp/libvips` packages with LGPL-3.0-or-later components

This means the repository itself can be MIT-licensed, but downstream redistributors must still comply with any third-party dependency terms that apply to the packages they ship.

## Runtime Disclosure Endpoints

The runtimes expose:

- `/license`
- `/health`

VDB startup also requires a one-time MIT acceptance recorded from an interactive `y` or `Y` response. This is only an open-source license acknowledgement. It does not enable any paid or commercial mode.

## Warranty and Liability Disclaimer

The software is provided **"AS IS"**, without warranty of any kind.
The author is not liable for damages resulting from use of the software.
