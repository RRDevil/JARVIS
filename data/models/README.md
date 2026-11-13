# J.A.R.V.I.S. Voice & Neural Models Storage

Large binary models are stored externally to keep the repository lightweight and comply with GitHub's 100 MB file size limit.

## Default Locations
By default, J.A.R.V.I.S. scans for model assets in:
1. `JARVIS_MODELS_DIR` environment variable (e.g. `../JARVIS_MODELS` or `D:\Raihan\JARVIS_MODELS`)
2. Sibling directory `../JARVIS_MODELS`
3. User directory `~/.jarvis/models`
4. User voices directory `D:\Raihan\Voices`

## Managing Models via the App
You can configure external storage paths or import models (.onnx Piper voicepacks, .pth/.index RVC models, Faster-Whisper STT) directly from the in-app **Settings HUD**:
- Open **Settings** -> **External Voice Models Storage**
- Click **Update Path** to set any custom drive/folder location.
- Use **Import Local Model Asset** to import loose model files, directories, or zip archives.
