# Compatibility

| Item | Status |
|---|---|
| Windows, ComfyUI 0.35.1 | Tested development environment; focused release also checked there. |
| Python 3.14.6, Torch 2.11.0+cu128 | Tested in the installed ComfyUI environment. |
| Python 3.12.14 | Offline geometry/regression test environment. |
| Other Python/ComfyUI versions | Unverified; require `comfy_api.latest.Types.MESH` and compatible dependency wheels. |
| Linux/macOS | Unverified. Manual installation instructions are provided, not a tested support claim. |
| NVIDIA GPU | Used by the upstream test environment; this pack's capture/Poisson/checks run on CPU. A CUDA GPU is not required by these kernels. |
| 32 GB system RAM | Development machine. Peak RAM depends on source faces, sampling and octree depth; no universal minimum is established. |
| Built-in `SaveGLB` | Used by supplied visual workflows. If absent, update ComfyUI or substitute a compatible MESH exporter. |
| Pixal3D/Trellis and other mesh generators | Connect a modern ComfyUI triangular MESH. The measured real-model test used a baseline-cleaned GLB, not every generator's raw output. |
| Astra original Visibility/Repair/Shell Polish | Optional upstream nodes. This pack does not replace or bundle them. |
| `astra_trusted_surface` development pack | Duplicate node IDs: do not load both packs. v0.4.1 development users can use the From_MESH workflow directly. The demo loader belongs to this standalone pack. |
| Textures, UVs, animation, rigs | Not preserved in reconstructed output. Geometry-only static mesh workflow. |
| Multiple batch items / point-only PLY | Not supported. The loader accepts triangle meshes and flattens static scene geometry/transforms. |

## Actual tested libraries

| Library | ComfyUI environment | Offline test environment |
|---|---|---|
| NumPy | 2.4.4 | 2.5.3 |
| SciPy | 1.18.0 | 1.18.1 |
| trimesh | 4.12.2 | 5.1.1 |
| rtree | 1.4.1 | 1.4.1 |
| PyMeshLab | 2025.7.post1 | 2025.7.post1 |

`requirements.txt` permits compatible ranges; it is not an exhaustive matrix of tested combinations. Optional `embreex`, where supported, can accelerate trimesh ray queries. The rtree-backed fallback is supported but can be much slower. No new Torch/CUDA installation is requested by this release.
