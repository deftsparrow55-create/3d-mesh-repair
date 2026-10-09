# Astra Forge: Exterior Poisson Repair for ComfyUI — v0.4.1 public beta

We've been developing a practical cleanup path for AI-generated resin miniatures: keep recognizable exterior detail, rebuild a closed surface, and remove enclosed geometry without turning the model into voxel terraces.

This release packages the method that produced the most usable results in our testing: **camera-visible oriented surface samples → screened Poisson reconstruction → bounded cleanup → enclosed-shell removal → geometry checks**.

Earlier binary-voxel filling and skin/core experiments cleaned volume but damaged exterior definition. This focused package leaves those experiments out. It reconstructs a continuous surface from the visible original geometry instead.

## What's included

- Four ComfyUI nodes: mesh loader, exterior capture, screened Poisson repair, and report display.
- A standalone visual workflow with a synthetic test mesh.
- An integration workflow for an existing MESH output, plus a labeled API prompt.
- Working settings, scale guidance, troubleshooting and a tested compatibility table.
- Windows installer, dependency checker, regression tests and SHA-256 manifest.
- MIT-licensed authored code. Dependencies are installed separately.

Download **AstraForge_Exterior_Poisson_v0.4.1.zip** from this release's assets, extract the folder into `ComfyUI/custom_nodes`, install its requirements with ComfyUI's Python, copy the included demo to `input/3d`, and restart. Full instructions are in the archive's README.

## Working miniature preset

**Capture:** 48 views, grid 2048, spacing 0.03 mm, hit tolerance 0.01 mm, 4096 MiB allowance, 2,000,000 probes.

In Capture's bottom settings text box:

```json
{"sampling_mode":"area_budgeted","target_patches":500000}
```

**Poisson:** depth 10, point weight 16, confidence 0.5, eight threads.

Scale must match the input: `units_to_mm = intended millimeter height / source coordinate height`. Use 1 for meshes already in mm. Our roughly unit-height normalized miniature used approximately 40. The output retains its original coordinate scale.

The probe count and patch count are different: **four probes are required per patch**. A 300,000-probe budget permits only 75,000 patches. This distinction caused misleading quality comparisons during development; the included settings guide spells it out.

## What we observed

On one supplied approximately 40 mm baseline-cleaned miniature, the denser preset reconstructed from 284,737 accepted exterior samples in about 65 seconds including capture and checks. It removed six enclosed shells and produced a 922,652-face result with no detected boundary/nonmanifold geometry, winding conflicts, duplicate/degenerate faces, self-intersections or nested shells. Five exterior components remained for attachment, trimming or supports.

The result was workable in sculpting software, with recognizable detail and a clean interior. Some edges softened. Increasing patch count to 750,000 or point weight to 24 did not visibly improve that example, so 500,000 / depth 10 / weight 16 remains the recommended starting point.

This is a public beta, not a guarantee for arbitrary triangle soup. Numerical checks can pass while intended gaps, fine features, or separate parts still need review. `UNKNOWN` is expected after successful screening because the tests are not exact mathematical or structural certification. Detected geometry failures block export.

## Compatibility and integration

Tested development environment: Windows, ComfyUI 0.35.1, Python 3.14.6 and Torch 2.11.0+cu128. Offline geometry tests also used Python 3.12.14. Other platforms/releases are listed as unverified. This pack's geometry operations run on CPU; a CUDA GPU is only needed if your upstream generator requires one.

The benchmark used a cleaned Pixal3D/Trellis-derived GLB. Any generator can feed a compatible triangular ComfyUI MESH, but raw-output quality varies. Original Astra visibility/repair/polish nodes can stay upstream; they are not bundled or required for the standalone file workflow. Textures, UVs and rigs are not reconstructed.

If you already use the development `astra_trusted_surface` pack at v0.4.1, use the From_MESH workflow with it rather than installing both packs: the core node IDs are shared intentionally.

For useful issue reports, include the input mesh, saved workflow, capture and repair reports, dependency versions and intended physical scale. We're particularly interested in thin weapons, hair, deep folds and limb gaps across different character generations.
