"""Read dependency/API availability; optionally reconstruct the bundled synthetic mesh."""
import argparse
import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--comfy-root',type=Path)
parser.add_argument('--run-demo',action='store_true')
args=parser.parse_args()
if args.comfy_root:sys.path.insert(0,str(args.comfy_root.resolve()))
root=Path(__file__).resolve().parents[1]
versions={}
for name in ('numpy','scipy','trimesh','rtree','pymeshlab','torch'):
    try:versions[name]=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:versions[name]='MISSING'
print(json.dumps({'python':sys.version.split()[0],'dependencies':versions},indent=2),flush=True)
spec=importlib.util.spec_from_file_location('astra_public_install_check',root/'__init__.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
if module.pymeshlab is None:raise RuntimeError('PyMeshLab could not import; inspect its native-library error in ComfyUI startup')
if 'generate_surface_reconstruction_screened_poisson' not in module.pymeshlab.filter_list():
    raise RuntimeError('Installed PyMeshLab lacks the screened Poisson filter')
if module.Types is None:raise RuntimeError('ComfyUI Types.MESH unavailable; use --comfy-root and the ComfyUI interpreter')
assert len(module.NODE_CLASS_MAPPINGS)==4
print('ComfyUI MESH API, PyMeshLab filter and four node definitions available',flush=True)
if args.run_demo:
    v,f=module.load_mesh_from_input(root/'examples','Astra_Demo_Open_Skin.glb')
    mesh=module._output(v,f,1.)
    _,ref,_,_=module.AstraCaptureExteriorReferenceV1().run(mesh,1.,48,2048,.03,.01,2000000,4096,
                                    '{"sampling_mode":"area_budgeted","target_patches":500000}')
    repaired,report,_=module.AstraExteriorPoissonRepairV1().run(ref,10,16.,.5,8)
    rv,rf=module._extract_single_mesh(repaired)
    out=Path.cwd()/'astra_install_check';out.mkdir(exist_ok=True)
    module._tm(rv,rf).export(out/'Astra_Demo_Repaired.glb')
    (out/'report.json').write_text(report.text(),encoding='utf-8')
    assert not report.failures
    print(report.text(),flush=True)
    print('Demo capture, reconstruction, MESH adapters and export passed:',out,flush=True)
