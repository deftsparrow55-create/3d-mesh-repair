import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import pytest
import trimesh

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('astra_public_tests',ROOT/'__init__.py')
astra=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=astra;SPEC.loader.exec_module(astra)

@pytest.fixture(scope='module')
def sphere():return trimesh.creation.icosphere(subdivisions=1,radius=2.)

@pytest.fixture(scope='module')
def reference(sphere):
    return astra.capture_reference(sphere.vertices,sphere.faces,views=20,grid=32,
                                    spacing=.5,epsilon=.001,max_samples=100000)

def test_capture_preserves_full_source(sphere,reference):
    np.testing.assert_array_equal(reference.vertices,sphere.vertices)
    np.testing.assert_array_equal(reference.faces,sphere.faces)
    assert not reference.vertices.flags.writeable

def test_probe_budget_caps_patch_count(sphere):
    ref=astra.capture_reference(sphere.vertices,sphere.faces,views=14,grid=32,spacing=.1,
               max_samples=400,sampling_mode='area_budgeted',target_patches=1000)
    assert len(ref.patches)<=100
    assert ref.report.metrics['sampling_budget_patches']==100

def test_hidden_inner_shell_not_used_as_exterior(sphere):
    inner=astra._tm(sphere.vertices*.4,sphere.faces)
    source=trimesh.util.concatenate([sphere,inner])
    ref=astra.capture_reference(source.vertices,source.faces,views=20,grid=32,spacing=.5,
                                max_samples=100000)
    assert not (ref.confidence[ref.face_ids>=len(sphere.faces)]>.1).any()

def test_poisson_produces_screened_closed_surface(reference):
    v,f,report=astra.reconstruct_exterior_poisson(reference,depth=6,threads=2)
    assert not report.failures and report.metrics['boundary_edges']==0
    assert report.metrics['nested_shells']==0

def test_cleanup_does_not_merge_close_exterior_solids():
    first=trimesh.creation.box();second=trimesh.creation.box();second.apply_translation([1.000003,0,0])
    source=trimesh.util.concatenate([first,second])
    mesh,_=astra._clean_poisson_output(source.vertices,source.faces,1.)
    metrics,failures,_=astra._topology_stats(mesh.vertices,mesh.faces)
    assert not failures and metrics['components']==2

def test_containment_removes_inner_but_keeps_external_piece(sphere):
    inside=astra._tm(sphere.vertices*.4,sphere.faces)
    outside=astra._tm(sphere.vertices+np.array([6,0,0]),sphere.faces)
    mesh,count=astra._remove_enclosed_components(trimesh.util.concatenate([sphere,inside,outside]))
    assert count==1 and len(mesh.split())==2

def test_loader_applies_scene_transform(tmp_path):
    box=trimesh.creation.box(extents=[1,2,3])
    scene=trimesh.Scene();transform=np.eye(4);transform[:3,3]=[5,2,0]
    scene.add_geometry(box,transform=transform)
    scene.export(tmp_path/'scene.glb')
    v,f=astra.load_mesh_from_input(tmp_path,'scene.glb')
    np.testing.assert_allclose(v.min(axis=0),[4.5,1,-1.5])
    assert len(f)==12

def test_loader_rejects_input_escape(tmp_path):
    with pytest.raises(ValueError,match='inside ComfyUI/input'):
        astra.load_mesh_from_input(tmp_path,'../other.glb')

def test_missing_solver_is_blocked(reference,monkeypatch):
    monkeypatch.setattr(astra,'pymeshlab',None)
    with pytest.raises(RuntimeError,match='requires PyMeshLab'):
        astra.reconstruct_exterior_poisson(reference)

def test_workflow_links_and_registered_nodes():
    for name in ('Astra_Exterior_Poisson_Demo.json','Astra_Exterior_Poisson_From_MESH.json'):
        w=json.loads((ROOT/'workflow'/name).read_text())
        nodes={n['id']:n for n in w['nodes']}
        for n in nodes.values():assert n['type'] in astra.NODE_CLASS_MAPPINGS or n['type']=='SaveGLB'
        for link,a,ao,b,bi,t in w['links']:
            assert link in nodes[a]['outputs'][ao]['links']
            assert nodes[b]['inputs'][bi]['link']==link

def test_focused_registry():
    assert set(astra.NODE_CLASS_MAPPINGS)=={'AstraLoadExteriorMeshV1','AstraCaptureExteriorReferenceV1',
                                          'AstraExteriorPoissonRepairV1','AstraTrustedReportV1'}
    assert 'AstraBuildVoidFreeSolidV1' not in astra.NODE_CLASS_MAPPINGS
