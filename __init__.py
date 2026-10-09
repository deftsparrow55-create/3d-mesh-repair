"""Astra Forge Exterior Poisson v0.4.1, public beta, MIT licensed.
Continuous exterior reconstruction from camera-visible oriented samples.
See README.md before installation; do not install alongside astra_trusted_surface.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from dataclasses import dataclass
import numpy as np
import trimesh
from scipy import sparse
from scipy.sparse import csgraph
try:
    import pymeshlab
except Exception:
    pymeshlab=None
try:
    import torch
    from comfy_api.latest import Types
except ImportError:
    torch=None
    Types=None
__version__="0.4.1"
SCHEMA=1
CATEGORY="Astra Forge/3D/Exterior Poisson"

def _positive(value, name):
    value = float(value)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return value

def _bounded(value, name, lo, hi):
    value = float(value)
    if not np.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}]")
    return value

def _readonly(a, dtype=None):
    a = np.array(a, dtype=dtype, copy=True, order="C")
    a.flags.writeable = False
    return a

def _hash(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        a = np.ascontiguousarray(a)
        h.update(str((a.dtype.str, a.shape)).encode())
        h.update(a.tobytes())
    return h.hexdigest()

def _mesh_hash(v, f):
    return _hash(np.asarray(v, np.float64), np.asarray(f, np.int64))

def _tm(v, f):
    return trimesh.Trimesh(vertices=np.array(v, copy=True),
                          faces=np.array(f, copy=True), process=False)

def _check_arrays(v, f):
    v, f = np.asarray(v), np.asarray(f)
    if v.ndim != 2 or v.shape[1] != 3 or f.ndim != 2 or f.shape[1] != 3:
        raise ValueError("Expected vertices [N,3] and triangular faces [F,3]")
    if len(v) == 0 or len(f) == 0:
        raise ValueError("Input mesh is empty")
    if not np.isfinite(v).all():
        raise ValueError("Input contains nonfinite vertices")
    if not np.issubdtype(f.dtype, np.integer):
        raise ValueError("Face indices must be integers")
    if f.min() < 0 or f.max() >= len(v):
        raise ValueError("Face index outside vertex array")
    if np.max(np.ptp(v, axis=0)) <= 0:
        raise ValueError("Mesh has zero bounds")
    return np.array(v, np.float64, copy=True), np.array(f, np.int64, copy=True)

def _extract_single_mesh(mesh):
    def array(x):
        if hasattr(x, "detach"):
            x = x.detach().cpu().numpy()
        return np.asarray(x)
    v, f = array(mesh.vertices), array(mesh.faces)
    for a, name in ((v, "vertices"), (f, "faces")):
        if a.ndim == 3 and a.shape[0] != 1:
            raise ValueError(f"Astra supports one mesh per batch ({name})")
    if v.ndim == 3:
        v = v[0]
    if f.ndim == 3:
        f = f[0]
    for attr, a in (("vertex_counts", v), ("face_counts", f)):
        counts = getattr(mesh, attr, None)
        if counts is not None:
            counts = array(counts).reshape(-1)
            if len(counts) != 1 or int(counts[0]) != counts[0]:
                raise ValueError(f"Invalid {attr}")
            n = int(counts[0])
            if n <= 0 or n > len(a):
                raise ValueError(f"Invalid {attr}")
            if attr == "vertex_counts":
                v = v[:n]
            else:
                f = f[:n]
    return _check_arrays(v, f)

def _output(v_mm, f, units):
    if Types is None or torch is None:
        raise RuntimeError("ComfyUI comfy_api.latest.Types.MESH is required for node outputs")
    v = np.asarray(v_mm / units, np.float32)
    return Types.MESH(vertices=torch.from_numpy(v.copy()).unsqueeze(0),
                      faces=torch.from_numpy(np.asarray(f, np.int64).copy()).unsqueeze(0))

def _roundtrip(v, units):
    return np.asarray(v / units, np.float32).astype(np.float64) * units

def _settings(text, defaults):
    value = json.loads(text or "{}")
    if not isinstance(value, dict):
        raise ValueError("Settings must be a JSON object")
    extra = set(value) - set(defaults)
    if extra:
        raise ValueError(f"Unsupported settings: {sorted(extra)}")
    return dict(defaults, **value)

@dataclass(frozen=True)
class QAReport:
    stage: str
    status: str
    metrics: dict
    failures: tuple = ()
    uncertainties: tuple = ()

    def text(self):
        return json.dumps({"schema": SCHEMA, "version": __version__,
                           "stage": self.stage, "status": self.status,
                           "metrics": self.metrics, "failures": self.failures,
                           "uncertainties": self.uncertainties}, indent=2)

@dataclass(frozen=True)
class SurfaceReference:
    vertices: np.ndarray
    faces: np.ndarray
    patches: np.ndarray  # tiny triangles, not original faces
    face_ids: np.ndarray
    normals: np.ndarray
    confidence: np.ndarray
    hits: np.ndarray
    geometry_hash: str
    fingerprint: str
    units: float
    spacing: float
    report: QAReport

def _report(stage, metrics, failures=(), uncertainties=()):
    return QAReport(stage, "FAIL" if failures else "UNKNOWN" if uncertainties else "PASS",
                    metrics, tuple(failures), tuple(uncertainties))

def _progress(stage, current=None, total=None):
    tail = "" if current is None else f" {current}/{total}"
    print(f"[Astra Trusted Surface] {stage}{tail}", flush=True)
    _cancel()

def _cancel():
    try:
        import comfy.model_management
        comfy.model_management.throw_exception_if_processing_interrupted()
    except ImportError:
        pass

def _directions(n):
    i = np.arange(int(n), dtype=float)
    y = 1 - 2 * (i + 0.5) / n
    radius = np.sqrt(1 - y*y)
    phi = np.pi * (3 - np.sqrt(5)) * i
    return np.column_stack((radius*np.cos(phi), y, radius*np.sin(phi)))

def _first_hits(mesh, origins, directions, chunk=8192):
    distance = np.full(len(origins), np.inf)
    ids = np.full(len(origins), -1, dtype=np.int64)
    for start in range(0, len(origins), chunk):
        _cancel()
        end = min(start + chunk, len(origins))
        try:
            tri, ray, loc = mesh.ray.intersects_id(
                origins[start:end], directions[start:end],
                return_locations=True, multiple_hits=False)
        except (ImportError, ModuleNotFoundError) as e:
            raise RuntimeError("Exact triangle rays require rtree; install requirements.txt in Comfy's Python") from e
        if len(ray):
            t = np.einsum("ij,ij->i", loc - origins[start:end][ray], directions[start:end][ray])
            distance[start + ray] = t
            ids[start + ray] = tri
    return distance, ids

def _split_triangles(tri):
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab, bc, ca = (a+b)/2, (b+c)/2, (c+a)/2
    return np.concatenate((np.stack((a,ab,ca), axis=1),
                           np.stack((ab,b,bc), axis=1),
                           np.stack((ca,bc,c), axis=1),
                           np.stack((ab,bc,ca), axis=1)))

def _edge_lengths(tri):
    return np.linalg.norm(tri - np.roll(tri, -1, axis=1), axis=2)

def _patches(v, f, spacing, max_patches):
    tri = v[f]
    area2 = np.linalg.norm(np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0]), axis=1)
    valid = area2 > max(np.max(np.ptp(v, axis=0))**2 * 1e-14, 1e-18)
    stack = [(tri[valid], np.flatnonzero(valid))]
    result, indices, count = [], [], 0
    while stack:
        t, ids = stack.pop()
        small = _edge_lengths(t).max(axis=1) <= spacing
        if small.any():
            count += int(small.sum())
            if count > max_patches:
                raise RuntimeError("Capture sample budget exceeded: increase spacing/grid pixel size or max_samples")
            result.append(t[small]); indices.append(ids[small])
        big = t[~small]
        if len(big):
            if count + 4*len(big) > max_patches:
                raise RuntimeError("Capture sample budget exceeded: increase sample_spacing_mm or max_samples")
            # Bound temporary allocations; preserve original face IDs through splitting.
            for start in range(0, len(big), 2048):
                bt = big[start:start+2048]
                bi = ids[~small][start:start+2048]
                stack.append((_split_triangles(bt), np.tile(bi, 4)))
    if not result:
        raise ValueError("No nondegenerate triangles to capture")
    return np.concatenate(result), np.concatenate(indices), int((~valid).sum())

def _area_sampled_patches(v, f, spacing, budget):
    """Deterministic surface-area samples, independent of source tessellation.

    Full source triangles remain occluders. Small source faces are sampled whole;
    larger ones contribute bounded interior patches, never synthesized bridges.
    """
    tri = v[f]
    area2 = np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
    eps = max(np.max(np.ptp(v,axis=0))**2*1e-14,1e-18)
    valid = area2>eps
    total = float(area2[valid].sum())
    if not np.isfinite(total) or total<=0:
        raise ValueError("No nondegenerate surface to sample")
    valid_ids = np.flatnonzero(valid)
    cumulative = np.cumsum(area2[valid])
    # Random positions inside equal-area strata avoid bias from face ordering.
    rng = np.random.default_rng(0)
    locations = (np.arange(budget)+rng.random(budget))*total/budget
    sampled_indices = np.minimum(np.searchsorted(cumulative,locations,side="right"),len(valid_ids)-1)
    ids = valid_ids[sampled_indices]
    lengths = _edge_lengths(tri[ids]).max(axis=1)
    small = lengths<=spacing
    # Do not spend repeated probes on identical tiny triangles.
    small_ids = np.unique(ids[small])
    big_ids = ids[~small]
    selected = tri[big_ids]
    root = np.sqrt(rng.random(len(big_ids)))
    along = rng.random(len(big_ids))
    bary = np.column_stack((1-root,root*(1-along),root*along))
    centers = np.einsum("ni,nij->nj",bary,selected)
    scale = np.minimum(1.,spacing/lengths[~small])
    patches = centers[:,None,:]+scale[:,None,None]*(selected-centers[:,None,:])
    patches = np.concatenate((tri[small_ids],patches))
    ids = np.concatenate((small_ids,big_ids))
    return patches,ids,int((~valid).sum())

def capture_reference(v, f, units=1.0, views=132, grid=512, spacing=0.1,
                      epsilon=0.02, max_samples=2000000, memory_mb=4096,
                      ray_chunk=8192, sampling_mode="strict", target_patches=200000):
    v, f = _check_arrays(v, f)
    units = _positive(units, "units_to_mm")
    spacing = _positive(spacing, "sample_spacing_mm")
    epsilon = _positive(epsilon, "depth_epsilon_mm")
    views = int(_bounded(views, "view_directions", 1, 512))
    grid = int(_bounded(grid, "grid_resolution", 8, 2048))
    if max_samples < 4 or memory_mb <= 0 or ray_chunk <= 0:
        raise ValueError("Invalid sample/memory/ray chunk budget")
    if sampling_mode not in ("strict","auto","area_budgeted"):
        raise ValueError("sampling_mode must be strict, auto or area_budgeted")
    target_patches = int(_bounded(target_patches,"target_patches",1,4000000))
    v *= units
    mesh = _tm(v, f)
    center = (v.min(axis=0)+v.max(axis=0))/2
    radius = np.linalg.norm(v-center, axis=1).max()
    pixel = 2*radius / grid
    effective = max(spacing, pixel)
    # Reserve memory for full source arrays and the triangle accelerator as well
    # as patch/probe work. This is a preflight estimate, not a RAM guarantee.
    source_estimate = len(v)*64+len(f)*256
    remaining = int(memory_mb*1024**2)-source_estimate
    max_patches = min(int(max_samples)//4, max(0,remaining//1536))
    if max_patches<1:
        raise RuntimeError(f"Capture source has {len(f):,} faces; source/BVH estimate is "
                           f"{source_estimate/1024**2:.0f} MiB before samples, above the "
                           f"{memory_mb:,} MiB budget. Increase memory_budget_mb or use a "
                           "manageable reference mesh; changing max_samples alone will not help.")
    _progress(f"Capture preflight: {len(f):,} faces, at most {4*max_patches:,} probes; mode={sampling_mode}")
    sampled = sampling_mode=="area_budgeted"
    patch_limit = max_patches if sampling_mode=="strict" else min(max_patches,target_patches)
    if sampling_mode=="auto" and len(f)>patch_limit:
        sampled = True
    if not sampled:
        try:
            patches,face_ids,degenerates = _patches(v,f,effective,patch_limit)
        except RuntimeError as exc:
            if "sample budget" not in str(exc):
                raise
            if sampling_mode=="strict":
                raise RuntimeError(
                    f"Capture sample budget exceeded: {len(f):,} source faces need at least "
                    f"{4*len(f):,} probes before subdivision; current capacity is "
                    f"{4*max_patches:,}. Dense input cannot be fixed by spacing alone. "
                    'Use settings {"sampling_mode":"auto","target_patches":200000}, '
                    "or increase max_samples AND memory_budget_mb for strict coverage.") from exc
            sampled = True
    if sampled:
        _progress(f"Area-budgeted capture: sampling up to {patch_limit:,} patches against the full source")
        patches,face_ids,degenerates = _area_sampled_patches(v,f,effective,patch_limit)
    normal = np.cross(patches[:,1]-patches[:,0], patches[:,2]-patches[:,0])
    normal /= np.linalg.norm(normal, axis=1)[:,None]
    centers = patches.mean(axis=1)
    # Four interior probes: each near-corner plus centroid. Rays hit full ORIGINAL
    # triangles; this is not the old centroid depth-bin visibility approximation.
    probes = np.concatenate((0.85*patches + 0.15*centers[:,None,:], centers[:,None,:]), axis=1)
    points = probes.reshape(-1,3)
    own_face = np.repeat(face_ids, 4)
    hits = np.zeros((len(patches),4), dtype=np.uint16)
    best = np.zeros((len(patches),4), dtype=float)
    pos = np.zeros(len(patches)); neg = np.zeros(len(patches))
    launch = 3*radius + 10*epsilon
    for i, direction in enumerate(_directions(views)):
        if i % 8 == 0:
            _progress("Triangle visibility views", i+1, views)
        dirs = np.broadcast_to(-direction, points.shape)
        distance, ids = _first_hits(mesh, points + launch*direction, dirs, int(ray_chunk))
        # Wrong coincident sheet IDs are ambiguous and NOT accepted.
        visible = (ids == own_face) & (np.abs(distance-launch) <= epsilon)
        incidence = normal @ direction
        visible = visible.reshape(-1,4) & (np.abs(incidence[:,None]) >= 0.0872)
        hits += visible
        best = np.maximum(best, visible * np.abs(incidence[:,None]))
        vote = visible.sum(axis=1) * np.abs(incidence)
        pos += np.where(incidence >= 0, vote, 0)
        neg += np.where(incidence < 0, vote, 0)
    certainty = np.divide(np.abs(pos-neg), pos+neg, out=np.zeros_like(pos), where=(pos+neg)>0)
    normal *= np.where(pos >= neg, 1., -1.)[:,None]
    supported = (hits>0).all(axis=1)
    confidence = supported * certainty * np.sqrt(best.min(axis=1))
    confidence[certainty < 0.8] = 0
    metrics = {"patches": len(patches), "probes": len(points), "views": views,
               "effective_spacing_mm": effective, "pixel_pitch_mm": pixel,
               "visible_patches": int(supported.sum()), "degenerate_source_faces": degenerates,
               "bounds_mm": np.ptp(v, axis=0).tolist(), "units_to_mm": units,
               "source_faces": len(f), "sampling_mode": "area_budgeted" if sampled else "strict",
               "source_faces_sampled": len(np.unique(face_ids)),
               "sampled_surface_area_mm2": float(np.linalg.norm(np.cross(patches[:,1]-patches[:,0],
                                                                          patches[:,2]-patches[:,0]),axis=1).sum()/2),
               "sampling_budget_patches": patch_limit,
               "estimated_source_bvh_mib": source_estimate/1024**2,
               "capture_method": "four targeted first-hit triangle rays per micro-patch/view"}
    uncertainties = ["Finite camera/sample coverage; visibility is not topology proof"]
    if sampled:
        uncertainties.append("Bounded surface-area sampling: unprobed source geometry stays untrusted; original mesh is unchanged")
    report = _report("capture", metrics, uncertainties=uncertainties)
    fingerprint = _hash(v, f, patches, face_ids, confidence, hits, np.array([units,effective,epsilon,views]),
                        np.frombuffer(__version__.encode(),dtype=np.uint8))
    return SurfaceReference(_readonly(v), _readonly(f), _readonly(patches),
                            _readonly(face_ids), _readonly(normal), _readonly(confidence),
                            _readonly(hits), _mesh_hash(v,f), fingerprint, units, effective, report)

def _topology_stats(v, f):
    """Edge and vertex manifoldness using corner-link connected components."""
    v, f = _check_arrays(v,f)
    nf = len(f)
    cross = np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
    area2 = np.linalg.norm(cross,axis=1)
    eps = max(np.max(np.ptp(v,axis=0))**2*1e-14,1e-18)
    edges = np.stack((f,np.roll(f,-1,axis=1)),axis=-1).reshape(-1,2)
    canonical = np.sort(edges,axis=1)
    order = np.lexsort((canonical[:,1],canonical[:,0]))
    sorted_edges = canonical[order]
    starts = np.r_[0,np.flatnonzero(np.any(sorted_edges[1:]!=sorted_edges[:-1],axis=1))+1]
    counts = np.diff(np.r_[starts,len(edges)])
    pairs = starts[counts==2]
    e1, e2 = order[pairs],order[pairs+1]
    winding = int(np.count_nonzero(np.all(edges[e1]==edges[e2],axis=1)))
    # Corner number equals directed edge number: start vertex f.flatten().
    e1n = 3*(e1//3)+(e1%3+1)%3
    e2n = 3*(e2//3)+(e2%3+1)%3
    same = edges[e1,0]==edges[e2,0]
    row = np.r_[e1,e1n]
    col = np.r_[np.where(same,e2,e2n),np.where(same,e2n,e2)]
    graph = sparse.coo_matrix((np.ones(len(row),np.uint8),(row,col)),shape=(3*nf,3*nf)).tocsr()
    _, link = csgraph.connected_components(graph,directed=False)
    link_pairs = np.unique(np.column_stack((f.reshape(-1),link)),axis=0)
    _, rings = np.unique(link_pairs[:,0],return_counts=True)
    vertex_nonmanifold = int(np.count_nonzero(rings!=1))
    face_graph = sparse.coo_matrix((np.ones(len(e1),np.uint8),(e1//3,e2//3)),shape=(nf,nf)).tocsr()
    components, face_labels = csgraph.connected_components(face_graph,directed=False)
    volumes = []
    for component in range(components):
        faces = f[face_labels==component]
        local = v[faces]-v[f[face_labels==component,0]].mean(axis=0)
        volumes.append(float(np.einsum("ij,ij->i",local[:,0],np.cross(local[:,1],local[:,2])).sum()/6))
    metrics = {"vertices": len(v), "faces": nf, "boundary_edges": int((counts==1).sum()),
               "nonmanifold_edges": int((counts>2).sum()), "nonmanifold_vertices": vertex_nonmanifold,
               "winding_conflicts": winding, "degenerate_faces": int((area2<=eps).sum()),
               "duplicate_faces": nf-len(np.unique(np.sort(f,axis=1),axis=0)),
               "components": int(components), "component_volumes_mm3": volumes}
    failures = [k for k in ("boundary_edges","nonmanifold_edges","nonmanifold_vertices",
                            "winding_conflicts","degenerate_faces","duplicate_faces") if metrics[k]]
    if any(x<=eps**1.5 for x in volumes):
        failures.append("nonpositive_component_volume")
    return metrics, failures, face_labels

def _intersections(v, f):
    if pymeshlab is None:
        return None, "PyMeshLab unavailable: global self-intersection screening not run"
    try:
        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(vertex_matrix=np.asarray(v,np.float64),
                                  face_matrix=np.asarray(f,np.int32)))
        ms.compute_selection_by_self_intersections_per_face()
        return int(np.count_nonzero(ms.current_mesh().face_selection_array())), None
    except Exception as exc:
        return None, f"PyMeshLab intersection filter failed: {type(exc).__name__}: {exc}"

def _nested_shells(v, f, labels):
    n = int(labels.max())+1
    if n<2:
        return 0
    meshes = [_tm(v,f[labels==i]) for i in range(n)]
    nested = 0
    for i in range(n):
        point = v[f[labels==i][0]].mean(axis=0)[None,:]
        for j in range(n):
            if i!=j and meshes[j].contains(point)[0]:
                nested += 1
    return nested

def _thickness_screen(v, f, pitch, max_samples=2048):
    mesh = _tm(v,f)
    ids = np.unique(np.linspace(0,len(f)-1,min(len(f),int(max_samples))).astype(int))
    centers = v[f[ids]].mean(axis=1)
    normal = np.asarray(mesh.face_normals)[ids]
    epsilon = max(pitch*1e-4, np.max(np.ptp(v,axis=0))*1e-10)
    distance, tri = _first_hits(mesh,centers-normal*epsilon,-normal)
    valid = np.isfinite(distance) & (distance>epsilon) & (tri!=ids)
    return {"thickness_rays": len(ids), "thickness_hits": int(valid.sum()),
            "sampled_min_thickness_mm": float((distance[valid]+epsilon).min()) if valid.any() else None,
            "thickness_method": "stratified inward face-normal ray screening; not a global certificate"}

def validate_geometry(v, f, pitch=0.1, require_single=True, min_thickness=0.,
                      thickness_samples=2048, stage="geometry"):
    pitch = _positive(pitch,"validation pitch")
    min_thickness = _bounded(min_thickness,"min_thickness_mm",0,1000)
    if int(thickness_samples)<1:
        raise ValueError("thickness_samples must be >= 1")
    metrics, failures, labels = _topology_stats(v,f)
    metrics["requested_min_thickness_mm"] = min_thickness
    unknown = []
    if require_single and metrics["components"] != 1:
        failures.append("requires_single_component")
    crossing, error = _intersections(v,f)
    metrics["intersecting_faces"] = crossing
    if error:
        unknown.append(error)
    elif crossing:
        failures.append("self_intersections")
    # Containment is meaningful only for closed, consistently oriented shells.
    if not failures:
        nested = _nested_shells(v,f,labels)
        metrics["nested_shells"] = nested
        if nested:
            failures.append("nested_internal_shells")
    if min_thickness>0 and not failures:
        screen = _thickness_screen(v,f,pitch,thickness_samples)
        metrics.update(screen)
        if screen["sampled_min_thickness_mm"] is not None and screen["sampled_min_thickness_mm"] < min_thickness:
            failures.append("sampled_thickness_below_limit")
        if screen["thickness_hits"] < screen["thickness_rays"]:
            unknown.append("Some thickness rays had no usable opposite hit")
        unknown.append("Sampled thickness cannot certify all narrow regions")
    # Numerical MeshLab checks are useful for test meshes, not exact-predicate certification.
    unknown.append("Float64/PyMeshLab screening is not exact-predicate intersection certification")
    metrics["bounds_mm"] = np.ptp(v,axis=0).tolist()
    return _report(stage,metrics,failures,unknown)

def _require_screened(report, context, require_intersections=True):
    if report.failures:
        raise RuntimeError(f"{context} failed: {', '.join(report.failures)}\n{report.text()}")
    if require_intersections and report.metrics.get("intersecting_faces") is None:
        raise RuntimeError(f"{context} needs PyMeshLab intersection screening\n{report.text()}")

def _float(default,minimum=0.001,maximum=1000.,step=0.01):
    return ("FLOAT",{"default":default,"min":minimum,"max":maximum,"step":step})

def _int(default,minimum,maximum,step=1):
    return ("INT",{"default":default,"min":minimum,"max":maximum,"step":step})

class _Node:
    CATEGORY=CATEGORY
    FUNCTION="run"

class AstraCaptureExteriorReferenceV1(_Node):
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"mesh":("MESH",),"units_to_mm":_float(1.0,0.000001,1000000),
                "view_directions":_int(48,14,512),"grid_resolution":_int(2048,128,2048,64),
                "sample_spacing_mm":_float(0.03),"depth_epsilon_mm":_float(0.01,0.000001,10,0.001),
                "max_samples":_int(2000000,1000,16000000,1000),"memory_budget_mb":_int(4096,256,32768,256)},
                "optional":{"settings":("STRING",{"default":'{"sampling_mode":"area_budgeted","target_patches":500000}',"multiline":True})}}
    RETURN_TYPES=("MESH","ASTRA_SURFACE_REF","ASTRA_QA_REPORT","STRING")
    RETURN_NAMES=("original_mesh","surface_reference","capture_report","info")
    def run(self,mesh,units_to_mm,view_directions,grid_resolution,sample_spacing_mm,
            depth_epsilon_mm,max_samples,memory_budget_mb,settings="{}"):
        options=_settings(settings,{"ray_chunk":8192,"sampling_mode":"auto","target_patches":200000})
        v,f=_extract_single_mesh(mesh)
        ref=capture_reference(v,f,units_to_mm,view_directions,grid_resolution,sample_spacing_mm,
                              depth_epsilon_mm,max_samples,memory_budget_mb,**options)
        return mesh,ref,ref.report,ref.report.text()

def _remove_enclosed_components(mesh):
    """Remove only whole closed components with every vertex inside another shell."""
    parts=mesh.split(only_watertight=False)
    removed=[]
    for i,child in enumerate(parts):
        for j,parent in enumerate(parts):
            if i==j or not parent.is_watertight or not child.is_watertight: continue
            if not np.all(child.bounds[0]>=parent.bounds[0]) or not np.all(child.bounds[1]<=parent.bounds[1]): continue
            inside=True
            for start in range(0,len(child.vertices),16384):
                if not parent.contains(child.vertices[start:start+16384]).all():
                    inside=False;break
            if inside: removed.append(i);break
    keep=[p for i,p in enumerate(parts) if i not in removed]
    if not keep: raise RuntimeError("Component containment removed all geometry")
    return trimesh.util.concatenate(keep),len(removed)

def _clean_poisson_output(vertices,faces,units):
    """Prefer the finest weld that survives output-coordinate topology screening."""
    physical=_roundtrip(vertices,units)
    last=None
    for digits in (7,6,5,4):
        mesh=_tm(physical,faces)
        mesh.merge_vertices(digits_vertex=digits)
        mesh.update_faces(mesh.unique_faces())
        area_epsilon=max(np.max(np.ptp(physical,axis=0))**2*1e-14,1e-18)
        mesh.update_faces(np.asarray(mesh.area_faces)*2>area_epsilon)
        mesh.remove_unreferenced_vertices()
        if not len(mesh.faces): continue
        trimesh.repair.fix_normals(mesh,multibody=True)
        # Only tiny, closed, numerically flat pieces may be discarded, never arbitrary floaters.
        parts=mesh.split(only_watertight=False)
        kept=[];removed=0
        for part in parts:
            if (part.is_watertight and len(part.faces)<=16 and
                part.extents.max()<=.01 and abs(part.volume)<=area_epsilon**1.5):
                removed+=1
            else: kept.append(part)
        if not kept: continue
        mesh=trimesh.util.concatenate(kept)
        # Try without added caps first; only triangular/quad boundaries can be capped.
        for cap in (False,True):
            candidate=mesh.copy()
            if cap: trimesh.repair.fill_holes(candidate)
            trimesh.repair.fix_normals(candidate,multibody=True)
            candidate=_tm(_roundtrip(candidate.vertices,units),candidate.faces)
            metrics,failures,_=_topology_stats(candidate.vertices,candidate.faces)
            last=_report("poisson-cleanup",metrics,failures)
            if failures: continue
            crossing,error=_intersections(candidate.vertices,candidate.faces)
            if error or crossing:
                last=_report("poisson-cleanup",dict(metrics,intersecting_faces=crossing),
                             ["self_intersections"] if crossing else [],[error] if error else [])
                continue
            return candidate,dict(vertex_merge_bin_mm=10.**-digits,
                     cleanup_caps_attempted=cap,removed_numerical_zero_volume_components=removed)
    if last is None: raise RuntimeError("Poisson cleanup produced no usable geometry")
    raise RuntimeError("Poisson reconstruction failed geometry screening after bounded cleanup:\n"+last.text())

def reconstruct_exterior_poisson(reference,depth=10,point_weight=8.,min_confidence=.5,threads=8):
    if pymeshlab is None: raise RuntimeError("Exterior Poisson reconstruction requires PyMeshLab")
    depth=int(_bounded(depth,"octree_depth",6,11))
    point_weight=_bounded(point_weight,"point_weight",1,32)
    threshold=_bounded(min_confidence,"min_confidence",.1,1)
    threads=int(_bounded(threads,"threads",1,16))
    keep=reference.confidence>=threshold
    points=reference.patches[keep].mean(axis=1);normals=reference.normals[keep]
    if len(points)<100: raise RuntimeError("Too few trustworthy exterior samples; increase capture coverage")
    if not np.isfinite(points).all() or not np.isfinite(normals).all():
        raise ValueError("Exterior samples contain nonfinite positions/normals")
    _progress(f"Screened Poisson reconstruction: {len(points):,} exterior samples, depth {depth}")
    ms=pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=np.asarray(points,np.float64),
                              v_normals_matrix=np.asarray(normals,np.float64)))
    ms.generate_surface_reconstruction_screened_poisson(depth=depth,fulldepth=5,pointweight=point_weight,
                 samplespernode=1.5,iters=8,scale=1.1,threads=threads,preclean=True)
    m=ms.current_mesh()
    mesh,cleanup=_clean_poisson_output(m.vertex_matrix(),m.face_matrix(),reference.units)
    physical=np.asarray(mesh.vertices)
    # Cleanup has already screened closed topology and intersections before containment.
    mesh,removed=_remove_enclosed_components(mesh)
    physical=_roundtrip(mesh.vertices,reference.units)
    final=validate_geometry(physical,mesh.faces,reference.spacing,False,stage="exterior-poisson")
    _require_screened(final,"Exterior Poisson")
    report=_report("exterior-poisson",dict(final.metrics,exterior_samples=len(points),
                     octree_depth=depth,point_weight=point_weight,min_confidence=threshold,
                     removed_enclosed_components=removed,units_to_mm=reference.units,
                     **cleanup),uncertainties=final.uncertainties+(
                         "Poisson reconstructs a continuous surface; exact original face/detail preservation is not guaranteed",
                         "Finite camera coverage can miss deep recesses or synthesize closure across legitimate openings",
                         "Disconnected exterior parts retained; inspect attachment/supports manually",
                         "Containment uses numerical all-vertex ray screening on intersection-screened closed shells"))
    return physical/reference.units,np.asarray(mesh.faces,np.int64),report

class AstraExteriorPoissonRepairV1(_Node):
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"surface_reference":("ASTRA_SURFACE_REF",),
                            "octree_depth":_int(10,6,11),"point_weight":_float(16.,1,32),
                            "min_confidence":_float(.5,.1,1),"threads":_int(8,1,16)}}
    RETURN_TYPES=("MESH","ASTRA_QA_REPORT","STRING")
    RETURN_NAMES=("reconstructed_exterior","repair_report","info")
    def run(self,surface_reference,octree_depth,point_weight,min_confidence,threads):
        v,f,report=reconstruct_exterior_poisson(surface_reference,octree_depth,point_weight,min_confidence,threads)
        return _output(v*surface_reference.units,f,surface_reference.units),report,report.text()

class AstraTrustedReportV1(_Node):
    """Output node so a diagnostic workflow runs without an exporter."""
    OUTPUT_NODE=True
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"report":("ASTRA_QA_REPORT",)}}
    RETURN_TYPES=("STRING",)
    RETURN_NAMES=("report_text",)
    def run(self,report):
        text=report.text()
        print("[Astra Trusted Surface] "+text,flush=True)
        return {"ui":{"text":[text]},"result":(text,)}

def load_mesh_from_input(input_directory,relative_path):
    from pathlib import Path
    base=Path(input_directory).resolve()
    path=(base/relative_path).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Mesh path must stay inside ComfyUI/input")
    if path.suffix.lower() not in {".glb",".gltf",".obj",".stl",".ply"}:
        raise ValueError("Use GLB, GLTF, OBJ, STL or PLY")
    if not path.is_file():
        raise FileNotFoundError("Copy the mesh into ComfyUI/input, then enter its relative path: "+relative_path)
    mesh=trimesh.load(str(path),force="mesh",process=False)
    if not isinstance(mesh,trimesh.Trimesh):
        raise ValueError("File did not contain a triangular surface mesh")
    return _check_arrays(mesh.vertices,mesh.faces)

class AstraLoadExteriorMeshV1(_Node):
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"mesh_file":("STRING",{"default":"3d/Astra_Demo_Open_Skin.glb"})}}
    RETURN_TYPES=("MESH","STRING")
    RETURN_NAMES=("mesh","bounds_info")
    def run(self,mesh_file):
        import folder_paths
        v,f=load_mesh_from_input(folder_paths.get_input_directory(),mesh_file)
        info=json.dumps({"bounds_source_units":np.ptp(v,axis=0).tolist(),"vertices":len(v),"faces":len(f),
                         "scale_note":"Capture units_to_mm = intended mm height / source height on the upright axis"},indent=2)
        return _output(v,f,1.),info

NODE_CLASS_MAPPINGS={cls.__name__:cls for cls in (
    AstraLoadExteriorMeshV1,AstraCaptureExteriorReferenceV1,AstraExteriorPoissonRepairV1,AstraTrustedReportV1)}
NODE_DISPLAY_NAME_MAPPINGS={
    "AstraLoadExteriorMeshV1":"Astra · Load Exterior Mesh",
    "AstraCaptureExteriorReferenceV1":"Astra · Capture Exterior Samples",
    "AstraExteriorPoissonRepairV1":"Astra · Exterior Screened Poisson Repair",
    "AstraTrustedReportV1":"Astra · Show Repair Report"}
WEB_DIRECTORY="./web"
__all__=["NODE_CLASS_MAPPINGS","NODE_DISPLAY_NAME_MAPPINGS"]
