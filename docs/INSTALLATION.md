# Installation

## Windows installer

Extract the release ZIP to a working folder. From PowerShell, run the installer with the **ComfyUI directory containing `main.py` and `custom_nodes`**:

```powershell
& "C:\Downloads\astra_exterior_poisson\INSTALL_WINDOWS.ps1" -ComfyRoot "C:\ComfyUI"
```

It looks for `venv\Scripts\python.exe` or a portable installation's sibling `python_embeded\python.exe`. For another environment, specify its interpreter:

```powershell
& "C:\Downloads\astra_exterior_poisson\INSTALL_WINDOWS.ps1" -ComfyRoot "C:\ComfyUI" -PythonExe "C:\my-env\Scripts\python.exe"
```

The script installs requirements, copies this pack into `custom_nodes`, and copies the demo into `input/3d`. It does not restart ComfyUI or overwrite an existing pack. If it detects `astra_trusted_surface`, it stops to avoid duplicate node registrations. Existing development users should keep their installed v0.4.1 pack and use the From_MESH workflow, or back up their development installation before manually switching to this focused pack.

If PowerShell blocks the script, use the manual steps below; no policy change is required.

## Manual Windows installation

Copy `astra_exterior_poisson` to `ComfyUI/custom_nodes`. Install with ComfyUI's interpreter:

```powershell
& "C:\ComfyUI\venv\Scripts\python.exe" -m pip install -r "C:\ComfyUI\custom_nodes\astra_exterior_poisson\requirements.txt"
```

Portable example:

```powershell
& "C:\ComfyUI_windows_portable\python_embeded\python.exe" -m pip install -r "C:\ComfyUI_windows_portable\ComfyUI\custom_nodes\astra_exterior_poisson\requirements.txt"
```

Copy the demo GLB into `ComfyUI/input/3d`, restart ComfyUI, refresh the browser, and import the demo workflow.

## Linux/macOS manual installation — not validated in this release

Copy the folder to `ComfyUI/custom_nodes/astra_exterior_poisson`, then use the active ComfyUI environment:

```sh
python -m pip install -r custom_nodes/astra_exterior_poisson/requirements.txt
mkdir -p input/3d
cp custom_nodes/astra_exterior_poisson/examples/Astra_Demo_Open_Skin.glb input/3d/
```

Wheel availability and PyMeshLab's native dependencies vary. These platforms remain unverified; check the startup log and run the install check before trying a large mesh.

## Check your installation

Using the same interpreter as ComfyUI:

```powershell
& "C:\ComfyUI\venv\Scripts\python.exe" "C:\ComfyUI\custom_nodes\astra_exterior_poisson\tools\check_install.py" --comfy-root "C:\ComfyUI"
```

Add `--run-demo` to exercise capture and reconstruction without queueing generation models. It writes an inspection GLB and report under the current working directory's `astra_install_check` folder. This check does not start a server or change your active workflow.

There is no published ComfyUI Manager/Registry entry in this package. Use manual installation or the included Windows script.
