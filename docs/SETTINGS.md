# Settings and tuning

Use the README's depth-10 / point-weight-16 / 500,000-patch preset first. Compare the same mesh and preserve the first successful export.

## Capture

| Control | Meaning |
|---|---|
| `units_to_mm` | Millimeters per source coordinate unit; affects sample spacing and reconstruction scale. |
| `view_directions` | Number of distributed camera directions. Finite views can miss occluded recesses. |
| `grid_resolution` | Contributes a minimum effective sample spacing based on object radius; it is not the Poisson grid. |
| `sample_spacing_mm` | Requested patch scale. Smaller does not guarantee denser coverage if the budget is capped. |
| `depth_epsilon_mm` | Allowed first-hit position tolerance; not a hole-depth threshold. |
| `max_samples` | Total four-probe budget. Divide by four for maximum patches, before memory limits. |
| `memory_budget_mb` | Preflight allowance for original geometry, BVH and sample buffers, not a guaranteed peak-memory cap. |
| JSON `target_patches` | Requested area-budgeted patch count. Edit the multiline `settings` box at the bottom of Capture. |

| Requested patches | `target_patches` | Minimum `max_samples` |
|---:|---:|---:|
| 300,000 | 300000 | 1200000 |
| 500,000 | 500000 | 2000000 |
| 750,000 | 750000 | 3000000 |

Example:

```json
{"sampling_mode":"area_budgeted","target_patches":500000}
```

`area_budgeted` is deterministic bounded sampling against the full original mesh. `auto` uses strict subdivision where the budget permits and switches to bounded sampling if necessary. `strict` requires full patch coverage and can fail on multi-million-face inputs. The release workflows deliberately use `area_budgeted`.

## Reconstruction

| Control | Starting point | Tradeoff |
|---|---:|---|
| `octree_depth` | 10 | Higher depth permits finer reconstruction but can retain more noise and require more memory. 11 is optional, not the default. |
| `point_weight` | 16 | Stronger sample-position fitting. Increasing to 24 produced little visible improvement in the development example. |
| `min_confidence` | 0.5 | Lower values admit uncertain samples and potentially unwanted geometry. |
| `threads` | 8 | CPU workers for PyMeshLab's solver. It does not make capture or every check multithreaded. |

More samples and depth cannot restore detail absent from the source or visible samples. No feature sharpening/projection pass is included. Edges may soften. Test one setting at a time; if 750,000 looks the same as 500,000, use 500,000.

## Scale and bases

Use `intended_height_mm / source_height` for the actual upright axis. A 0.97-unit model intended to be 40 mm tall needs approximately 41.24, not exactly 40. The loader reports the source bounding dimensions but cannot identify toe-to-eye height or distinguish a character from its base. The demo is already in millimeters and uses scale 1.

The output remains in original source units. Set final height in the slicer, and disable slicer hollowing if a filled print is intended. Layer height is not a structural wall-thickness threshold; this package does not impose the earlier experimental 0.6 mm cutoff.
