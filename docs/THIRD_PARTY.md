# Third-party components

The release contains Astra Forge authored Python, documentation, local report UI, workflows and synthetic geometry. The authored material is covered by the included MIT license.

Dependencies are installed separately: ComfyUI/Torch, NumPy, SciPy, trimesh, rtree and PyMeshLab. Reconstruction calls PyMeshLab's `generate_surface_reconstruction_screened_poisson` filter; this package does not reimplement or bundle that solver. Each dependency retains its own upstream license. Their distributions and license files are not replaced by this package's MIT license.

No uploaded character mesh, user screenshot, generation prompt, model weight, or original Astra cleanup ZIP is redistributed in this standalone release. The included demo is synthetic geometry generated specifically for this package.
