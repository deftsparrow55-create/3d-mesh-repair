# Release verification

Checked locally on 2026-10-09. These results establish the tested configurations, not universal compatibility.

## Focused standalone regression suite

**11 tests passed** using Python 3.12.14 and the offline dependencies listed in COMPATIBILITY.md. Coverage includes immutable original geometry, four-probe sampling budgets, hidden interior-shell rejection, closed Poisson output, fine cleanup preserving separate components, enclosed-shell removal, static scene transforms, input-path boundaries, missing-solver failure, workflow links, and the four-node registry.

Run from this package with its development requirements installed:

```sh
python -m pytest tests -q
```

The full development pack separately passed 56 tests before extracting this focused release.

## Actual ComfyUI interpreter and synthetic demo

Ran `tools/check_install.py --comfy-root <ComfyUI directory> --run-demo` using the installed Windows ComfyUI interpreter: Python 3.14.6, ComfyUI 0.35.1, Torch 2.11.0+cu128. This exercised the actual MESH input/output adapters, capture and repair node methods, dependency imports, native screened Poisson filter, numerical screening, and GLB export.

The bundled synthetic open-skin mesh, at the recommended 500,000-patch / depth-10 / weight-16 settings, produced:

| Measurement | Result |
|---|---:|
| Accepted exterior samples | 403,576 |
| Output vertices | 1,019,502 |
| Output faces | 2,039,000 |
| Retained exterior components | 1 |
| Removed enclosed components | 2 |
| Boundary / nonmanifold edges and vertices | 0 |
| Winding conflicts / duplicate / degenerate faces | 0 |
| Detected intersecting faces / nested shells | 0 |

Status remains `UNKNOWN` because the numerical screens do not certify exact geometry or structural printability. See `examples/Astra_Demo_Repair_Report.json` for the complete report. The full-resolution synthetic test can take several minutes; it is not the miniature timing benchmark.

## Packaging and installation helper

- PowerShell installer parsed without syntax errors.
- Its duplicate-development-pack guard was tested against a synthetic ComfyUI directory and stopped before installing dependencies.
- Visual workflow links and node IDs were checked in the regression suite. The workflows were not queued through the browser UI as part of this release check.
- ZIP integrity and each file's SHA-256 are checked during packaging; the release has an external ZIP checksum and an internal manifest.

A fresh-machine install, alternative platforms, all mesh generators, and every allowed dependency version have not been tested. The README's real-miniature measurements are separate development observations; that private mesh is not distributed.
