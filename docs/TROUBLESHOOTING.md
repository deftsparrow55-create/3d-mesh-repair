# Troubleshooting

**Missing nodes after restart:** inspect ComfyUI's startup log, install requirements with its own interpreter, and run `tools/check_install.py`. A terminal's unrelated global Python is not sufficient. Check that the package folder directly contains `__init__.py`; avoid a double nested ZIP folder.

**Duplicate node names:** do not install this focused pack alongside the development `astra_trusted_surface` pack. The core node IDs intentionally remain compatible.

**File not found:** Load Exterior Mesh reads relative to `ComfyUI/input`, not the package's `examples` directory. Copy the demo to `input/3d`, then use `3d/Astra_Demo_Open_Skin.glb`. Arbitrary paths outside the input directory are rejected.

**Missing MESH connection:** the From_MESH workflow is an integration fragment. Connect your existing MESH output to Capture. The Demo workflow includes a loader.

**Grainier or softer after changing "samples":** check both `target_patches` in the JSON box and `max_samples` above it. 500,000 patches need at least 2,000,000 probes. Reset depth 10, point weight 16, confidence 0.5 before comparison. Inspect the effective sampling budget in the capture report.

**Capture source/BVH budget exceeded:** increasing the probe count alone will not help. Use a manageable baseline mesh or increase the allowance if system RAM permits. Full source geometry remains a ray occluder; the code does not silently decimate it.

**Too few trusted points:** check scale, view coverage, source geometry and confidence. Incorrect scale can make a miniature's capture spacing inappropriate. Do not immediately lower confidence to accept unknown internal geometry.

**Poisson failed geometry screening:** output remains blocked. v0.4.1 tries bounded numerical cleanup and removes only microscopic closed zero-volume artifacts. It does not bypass nonmanifold/intersection failures or delete arbitrary exterior details. Return to the working preset. For a reproducible issue, attach the actual input mesh, saved workflow, report, dependency versions and physical scale.

**`UNKNOWN` with zero failures:** expected. Topology/intersection checks are numerical screening rather than exact proof. Reports list uncertainty separately from detected failures.

**Separate pieces remain:** intentional. The filter removes enclosed shells, not every small exterior object. Inspect and trim, join or support separate parts as appropriate.

**Slow capture:** ray backend, source complexity and view count matter. The optional Embreex backend is faster where its wheel is available. Higher sampling is not always visibly better.

**Definition still soft:** this implementation interpolates a continuous surface. It cannot guarantee exact sharp-edge preservation. Higher depth/point weight may also preserve noise. Compare the result in your sculpting application before applying more smoothing or remeshing.
