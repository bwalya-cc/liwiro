# Third-Party Licenses

This file inventories the third-party runtime dependencies shipped or bundled with this repository as of 2026-03-16.

## Scope

- Included: resolved frontend production dependencies from `liwiro/frontend/package-lock.json` and `liwiro/frontend/node_modules`
- Included: direct backend runtime dependencies declared in `liwiro/backend/requirements.txt`
- Included: pinned JVM runtime dependencies declared in `verun/vdb/pom.xml` and inherited by `verun/vi`
- Excluded: dev-only dependencies, test-only dependencies, and Maven build plugins that are not shipped in runtime artifacts
- Important: the Python backend uses version ranges rather than a checked-in lockfile, so the exact transitive Python dependency tree is not reproducibly fixed by this repository alone
- Important: many packages do not publish a normalized copyright field in manifest metadata; where that happens, the authoritative notice remains the package's own `LICENSE`, `COPYING`, or `NOTICE` file

## License References

- `0BSD`: <https://opensource.org/license/0bsd>
- `Apache-2.0`: <https://www.apache.org/licenses/LICENSE-2.0.txt>
- `BSD-3-Clause`: <https://opensource.org/license/bsd-3-clause>
- `CC-BY-4.0`: <https://creativecommons.org/licenses/by/4.0/legalcode>
- `ISC`: <https://opensource.org/license/isc-license-txt>
- `LGPL-3.0-or-later`: <https://www.gnu.org/licenses/lgpl-3.0.txt>
- `MIT`: <https://opensource.org/license/mit>
- `Python-2.0`: <https://docs.python.org/3/license.html>
- `ZPL-2.1`: <https://opensource.org/license/zpl-2-1>

## Frontend Direct Runtime Dependencies

These are the 48 direct runtime dependencies declared in `liwiro/frontend/package.json`. Versions, license identifiers, and notice-owner hints were read from the installed package metadata under `liwiro/frontend/node_modules`.

| Package | Version | License | Upstream notice owner | Homepage / repository |
| --- | --- | --- | --- | --- |
| @radix-ui/react-accordion | 1.2.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-alert-dialog | 1.1.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-aspect-ratio | 1.1.2 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-avatar | 1.1.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-checkbox | 1.1.4 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-collapsible | 1.1.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-context-menu | 2.2.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-dialog | 1.1.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-dropdown-menu | 2.1.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-hover-card | 1.1.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-label | 2.1.2 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-menubar | 1.1.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-navigation-menu | 1.2.5 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-popover | 1.1.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-progress | 1.1.2 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-radio-group | 1.2.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-scroll-area | 1.2.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-select | 2.1.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-separator | 1.1.2 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-slider | 1.2.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-slot | 1.1.2 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-switch | 1.1.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-tabs | 1.1.3 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-toast | 1.2.6 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-toggle | 1.1.2 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-toggle-group | 1.1.2 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @radix-ui/react-tooltip | 1.1.8 | MIT | See upstream license file | https://radix-ui.com/primitives |
| @xterm/addon-fit | 0.11.0 | MIT | The xterm.js authors | https://github.com/xtermjs/xterm.js/tree/master/addons/addon-fit |
| @xterm/xterm | 6.0.0 | MIT | See upstream license file | https://github.com/xtermjs/xterm.js |
| class-variance-authority | 0.7.1 | Apache-2.0 | Joe Bell (https://joebell.co.uk) | https://github.com/joe-bell/cva#readme |
| clsx | 2.1.1 | MIT | Luke Edwards | https://github.com/lukeed/clsx |
| cmdk | 1.0.4 | MIT | Paco | https://github.com/pacocoursey/cmdk#readme |
| date-fns | 3.6.0 | MIT | See upstream license file | https://github.com/date-fns/date-fns |
| embla-carousel-react | 8.5.1 | MIT | David Jerleke | https://www.embla-carousel.com |
| input-otp | 1.4.1 | MIT | Guilherme Rodz (g@rodz.dev) | https://input-otp.rodz.dev/ |
| lucide-react | 0.454.0 | ISC | Eric Fennis | https://lucide.dev |
| next | 15.2.4 | MIT | See upstream license file | https://nextjs.org |
| next-themes | 0.4.6 | MIT | See upstream license file | https://github.com/pacocoursey/next-themes.git |
| react | 19.1.0 | MIT | See upstream license file | https://react.dev/ |
| react-day-picker | 8.10.1 | MIT | Giampaolo Bellavite (io@gpbl.dev) | http://react-day-picker.js.org |
| react-dom | 19.1.0 | MIT | See upstream license file | https://react.dev/ |
| react-hook-form | 7.55.0 | MIT | Beier(Bill) Luo (bluebill1049@hotmail.com) | https://www.react-hook-form.com |
| react-resizable-panels | 2.1.7 | MIT | Brian Vaughn (brian.david.vaughn@gmail.com) | https://github.com/bvaughn/react-resizable-panels |
| recharts | 2.15.0 | MIT | recharts group | https://github.com/recharts/recharts |
| sonner | 1.7.4 | MIT | Emil Kowalski (e@emilkowal.ski) | https://sonner.emilkowal.ski/ |
| tailwind-merge | 2.6.0 | MIT | Dany Castillo | https://github.com/dcastil/tailwind-merge |
| tailwindcss-animate | 1.0.7 | MIT | Jamie Kyle (me@thejameskyle.com) | https://github.com/jamiebuilds/tailwindcss-animate |
| vaul | 0.9.9 | MIT | Emil Kowalski (e@emilkowal.ski) | https://vaul.emilkowal.ski/ |

## Frontend Resolved Production Dependency Tree

The resolved frontend production tree currently contains 180 packages. The notable licensing nuance is Next.js's optional `sharp` and `libvips` platform packages, which introduce `Apache-2.0`, `LGPL-3.0-or-later`, and mixed license expressions into the shipped tree.

- `0BSD` (1 packages): `tslib@2.8.1`
- `Apache-2.0` (13 packages): `@img/sharp-darwin-arm64@0.33.5`, `@img/sharp-darwin-x64@0.33.5`, `@img/sharp-linux-arm64@0.33.5`, `@img/sharp-linux-arm@0.33.5`, `@img/sharp-linux-s390x@0.33.5`, `@img/sharp-linux-x64@0.33.5`, `@img/sharp-linuxmusl-arm64@0.33.5`, `@img/sharp-linuxmusl-x64@0.33.5`, `@swc/counter@0.1.3`, `@swc/helpers@0.5.15`, `class-variance-authority@0.7.1`, `detect-libc@2.0.3`, `sharp@0.33.5`
- `Apache-2.0 AND LGPL-3.0-or-later` (2 packages): `@img/sharp-win32-ia32@0.33.5`, `@img/sharp-win32-x64@0.33.5`
- `Apache-2.0 AND LGPL-3.0-or-later AND MIT` (1 packages): `@img/sharp-wasm32@0.33.5`
- `BSD-3-Clause` (3 packages): `d3-ease@3.0.1`, `react-transition-group@4.4.5`, `source-map-js@1.2.1`
- `CC-BY-4.0` (1 packages): `caniuse-lite@1.0.30001707`
- `ISC` (14 packages): `d3-array@3.2.4`, `d3-color@3.1.0`, `d3-format@3.1.0`, `d3-interpolate@3.0.1`, `d3-path@3.1.0`, `d3-scale@4.0.2`, `d3-shape@3.2.0`, `d3-time-format@4.1.0`, `d3-time@3.1.0`, `d3-timer@3.0.1`, `internmap@2.0.3`, `lucide-react@0.454.0`, `picocolors@1.1.1`, `semver@7.7.4`
- `LGPL-3.0-or-later` (8 packages): `@img/sharp-libvips-darwin-arm64@1.0.4`, `@img/sharp-libvips-darwin-x64@1.0.4`, `@img/sharp-libvips-linux-arm64@1.0.4`, `@img/sharp-libvips-linux-arm@1.0.5`, `@img/sharp-libvips-linux-s390x@1.0.4`, `@img/sharp-libvips-linux-x64@1.0.4`, `@img/sharp-libvips-linuxmusl-arm64@1.0.4`, `@img/sharp-libvips-linuxmusl-x64@1.0.4`
- `MIT` (136 packages): `@babel/runtime@7.27.0`, `@emnapi/runtime@1.8.1`, `@floating-ui/core@1.6.9`, `@floating-ui/dom@1.6.13`, `@floating-ui/react-dom@2.1.2`, `@floating-ui/utils@0.2.9`, `@next/env@15.2.4`, `@next/swc-darwin-arm64@15.2.4`, `@next/swc-darwin-x64@15.2.4`, `@next/swc-linux-arm64-gnu@15.2.4`, `@next/swc-linux-arm64-musl@15.2.4`, `@next/swc-linux-x64-gnu@15.2.4`, `@next/swc-linux-x64-musl@15.2.4`, `@next/swc-win32-arm64-msvc@15.2.4`, `@next/swc-win32-x64-msvc@15.2.4`, `@radix-ui/number@1.1.0`, `@radix-ui/primitive@1.1.1`, `@radix-ui/react-accordion@1.2.3`, `@radix-ui/react-alert-dialog@1.1.6`, `@radix-ui/react-arrow@1.1.2`, `@radix-ui/react-aspect-ratio@1.1.2`, `@radix-ui/react-avatar@1.1.3`, `@radix-ui/react-checkbox@1.1.4`, `@radix-ui/react-collapsible@1.1.3`, `@radix-ui/react-collection@1.1.2`, `@radix-ui/react-compose-refs@1.1.1`, `@radix-ui/react-context-menu@2.2.6`, `@radix-ui/react-context@1.1.1`, `@radix-ui/react-dialog@1.1.6`, `@radix-ui/react-direction@1.1.0`, `@radix-ui/react-dismissable-layer@1.1.5`, `@radix-ui/react-dropdown-menu@2.1.6`, `@radix-ui/react-focus-guards@1.1.1`, `@radix-ui/react-focus-scope@1.1.2`, `@radix-ui/react-hover-card@1.1.6`, `@radix-ui/react-id@1.1.0`, `@radix-ui/react-label@2.1.2`, `@radix-ui/react-menu@2.1.6`, `@radix-ui/react-menubar@1.1.6`, `@radix-ui/react-navigation-menu@1.2.5`, `@radix-ui/react-popover@1.1.6`, `@radix-ui/react-popper@1.2.2`, `@radix-ui/react-portal@1.1.4`, `@radix-ui/react-presence@1.1.2`, `@radix-ui/react-primitive@2.0.2`, `@radix-ui/react-progress@1.1.2`, `@radix-ui/react-radio-group@1.2.3`, `@radix-ui/react-roving-focus@1.1.2`, `@radix-ui/react-scroll-area@1.2.3`, `@radix-ui/react-select@2.1.6`, `@radix-ui/react-separator@1.1.2`, `@radix-ui/react-slider@1.2.3`, `@radix-ui/react-slot@1.1.2`, `@radix-ui/react-switch@1.1.3`, `@radix-ui/react-tabs@1.1.3`, `@radix-ui/react-toast@1.2.6`, `@radix-ui/react-toggle-group@1.1.2`, `@radix-ui/react-toggle@1.1.2`, `@radix-ui/react-tooltip@1.1.8`, `@radix-ui/react-use-callback-ref@1.1.0`, `@radix-ui/react-use-controllable-state@1.1.0`, `@radix-ui/react-use-escape-keydown@1.1.0`, `@radix-ui/react-use-layout-effect@1.1.0`, `@radix-ui/react-use-previous@1.1.0`, `@radix-ui/react-use-rect@1.1.0`, `@radix-ui/react-use-size@1.1.0`, `@radix-ui/react-visually-hidden@1.1.2`, `@radix-ui/rect@1.1.0`, `@types/d3-array@3.2.1`, `@types/d3-color@3.1.3`, `@types/d3-ease@3.0.2`, `@types/d3-interpolate@3.0.4`, `@types/d3-path@3.1.1`, `@types/d3-scale@4.0.9`, `@types/d3-shape@3.1.7`, `@types/d3-time@3.0.4`, `@types/d3-timer@3.0.2`, `@xterm/addon-fit@0.11.0`, `@xterm/xterm@6.0.0`, `aria-hidden@1.2.4`, `busboy@1.6.0`, `client-only@0.0.1`, `clsx@2.1.1`, `cmdk@1.0.4`, `color-convert@2.0.1`, `color-name@1.1.4`, `color-string@1.9.1`, `color@4.2.3`, `csstype@3.1.3`, `date-fns@3.6.0`, `decimal.js-light@2.5.1`, `detect-node-es@1.1.0`, `dom-helpers@5.2.1`, `embla-carousel-react@8.5.1`, `embla-carousel-reactive-utils@8.5.1`, `embla-carousel@8.5.1`, `eventemitter3@4.0.7`, `fast-equals@5.2.2`, `get-nonce@1.0.1`, `input-otp@1.4.1`, `is-arrayish@0.3.2`, `js-tokens@4.0.0`, `lodash@4.17.21`, `loose-envify@1.4.0`, `nanoid@3.3.11`, `next-themes@0.4.6`, `next/node_modules/postcss@8.4.31`, `next@15.2.4`, `object-assign@4.1.1`, `prop-types/node_modules/react-is@16.13.1`, `prop-types@15.8.1`, `react-day-picker@8.10.1`, `react-dom@19.1.0`, `react-hook-form@7.55.0`, `react-is@18.3.1`, `react-remove-scroll-bar@2.3.8`, `react-remove-scroll@2.6.3`, `react-resizable-panels@2.1.7`, `react-smooth@4.0.4`, `react-style-singleton@2.2.3`, `react@19.1.0`, `recharts-scale@0.4.5`, `recharts@2.15.0`, `regenerator-runtime@0.14.1`, `scheduler@0.26.0`, `simple-swizzle@0.2.2`, `sonner@1.7.4`, `streamsearch@1.1.0`, `styled-jsx@5.1.6`, `tailwind-merge@2.6.0`, `tailwindcss-animate@1.0.7`, `tiny-invariant@1.3.3`, `use-callback-ref@1.3.3`, `use-sidecar@1.1.3`, `use-sync-external-store@1.5.0`, `vaul@0.9.9`
- `MIT AND ISC` (1 packages): `victory-vendor@36.9.2`

## Backend Python Runtime Dependencies

The backend dependency file is `liwiro/backend/requirements.txt`. Because the repository does not ship a Python lockfile, the exact resolved versions and transitive dependency set are environment-specific. The license names below were taken from upstream package metadata and project pages current on 2026-03-14.

| Package | Version specifier | License | Upstream |
| --- | --- | --- | --- |
| Flask | `>=3.0,<4.0` | BSD-3-Clause | https://pypi.org/project/Flask/ |
| flask-sock | `>=0.7,<1.0` | MIT | https://pypi.org/project/flask-sock/ |
| flask-cors | `>=4.0,<6.0` | MIT | https://pypi.org/project/flask-cors/ |
| requests | `>=2.31,<3.0` | Apache-2.0 | https://requests.readthedocs.io |
| python-dotenv | `>=1.0,<2.0` | BSD-3-Clause | https://pypi.org/project/python-dotenv/ |
| jsonschema | `>=4.0,<5.0` | MIT AND Python-2.0 | https://pypi.org/project/jsonschema/ |
| waitress | `>=3.0,<4.0` | ZPL-2.1 | https://pypi.org/project/waitress/ |
| psutil | `>=5.9,<8.0` | BSD-3-Clause | https://github.com/giampaolo/psutil |
| uvicorn | `>=0.30,<1.0` | BSD-3-Clause | https://pypi.org/project/uvicorn/ |
| PyJWT | `>=2.8,<3.0` | MIT | https://pypi.org/project/PyJWT/ |

## JVM Runtime Dependencies

The JVM runtime artifacts are built from `verun/vdb/pom.xml` and `verun/vi/pom.xml`. `verun:vi` depends on the local `verun:vdb` module, so the shipped third-party runtime set is the `vdb` runtime tree below. Test-only `junit-jupiter` is intentionally excluded.

| Package | Version | License | Upstream |
| --- | --- | --- | --- |
| com.google.code.gson:gson | `2.8.9` | Apache-2.0 | https://github.com/google/gson |
| org.mindrot:jbcrypt | `0.4` | ISC | https://github.com/djmdjm/jBCrypt |
