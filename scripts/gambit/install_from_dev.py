"""Install Gambit + plugins from dev laptop: download via nuget locally, push via Gambit file upload API."""
import httpx
import os
import glob
import time
import shutil

BASE = "http://192.168.0.4:22133"
NUGET_SOURCE = "https://pkgs.dev.azure.com/MSFTDEVICES/_packaging/Shared/nuget/v3/index.json"
LOCAL_STAGING = "C:\\Staging\\GambitDeploy"
REMOTE_PATH = "C:\\gambit"

PLUGINS = [
    "Gambit.Plugin.Audio",
    "Gambit.Plugin.Display",
    "Gambit.Plugin.Sensors",
    "Gambit.Plugin.ScreenCapture",
    "Gambit.Plugin.Injection",
    "Gambit.Plugin.PowerStateTransition",
    "Gambit.Plugin.Digitizer",
    "Gambit.Plugin.Digitizer.Firmware",
    "Gambit.Plugin.Streams.Raw",
]

def run_on_dut(cmd, args, timeout=30):
    r = httpx.post(f"{BASE}/Process/run", json={"Binary": cmd, "Args": args}, timeout=timeout)
    data = r.json()
    return data.get("Output", ""), data.get("Error", ""), data.get("ExitCode", -1)

def upload_file(local_path, remote_path):
    """Upload a file to the DUT via Gambit file upload API."""
    with open(local_path, "rb") as f:
        files = {"file": (os.path.basename(local_path), f)}
        r = httpx.post(f"{BASE}/file/upload", files=files,
                       params={"path": remote_path}, timeout=120)
    return r.status_code

print("=" * 60)
print("  INSTALL GAMBIT + PLUGINS (from dev laptop)")
print("=" * 60)

# Step 1: Download Gambit.App locally
print("\nStep 1: Downloading Gambit.App locally...")
if os.path.exists(LOCAL_STAGING):
    shutil.rmtree(LOCAL_STAGING)
os.makedirs(LOCAL_STAGING, exist_ok=True)

dl_dir = os.path.join(LOCAL_STAGING, "downloads")
os.makedirs(dl_dir, exist_ok=True)

ret = os.system(f'nuget install Gambit.App -Source "{NUGET_SOURCE}" -OutputDirectory "{dl_dir}" -PreRelease -NonInteractive')
print(f"  nuget exit: {ret}")

# Find content folder
gambit_dirs = glob.glob(os.path.join(dl_dir, "Gambit.App*"))
if gambit_dirs:
    gambit_dir = sorted(gambit_dirs)[-1]
    content_dir = os.path.join(gambit_dir, "content")
    if os.path.exists(content_dir):
        print(f"  Found content at: {content_dir}")
        gambit_files = os.listdir(content_dir)
        print(f"  Files: {gambit_files[:10]}")
    else:
        print(f"  No content subfolder in {gambit_dir}")
        print(f"  Contents: {os.listdir(gambit_dir)}")
        content_dir = None
else:
    print("  Gambit.App not downloaded!")
    content_dir = None

# Step 2: Download plugins locally
print("\nStep 2: Downloading plugins locally...")
plugin_dl = os.path.join(LOCAL_STAGING, "plugins_dl")
os.makedirs(plugin_dl, exist_ok=True)

for plugin in PLUGINS:
    print(f"  Downloading {plugin}...")
    ret = os.system(f'nuget install {plugin} -Source "{NUGET_SOURCE}" -OutputDirectory "{plugin_dl}" -PreRelease -NonInteractive')
    if ret == 0:
        pkg_dirs = sorted(glob.glob(os.path.join(plugin_dl, f"{plugin}*")))
        if pkg_dirs:
            print(f"    Downloaded: {os.path.basename(pkg_dirs[-1])}")
        else:
            print(f"    Package dir not found")
    else:
        print(f"    FAILED (exit {ret})")

# Step 3: Prepare C:\gambit on DUT
print("\nStep 3: Preparing C:\\gambit on DUT...")
run_on_dut("cmd.exe", f'/c taskkill /f /im Gambit.exe 2>nul')
time.sleep(2)
run_on_dut("cmd.exe", f'/c if exist {REMOTE_PATH} rmdir /s /q {REMOTE_PATH}')
time.sleep(1)
run_on_dut("cmd.exe", f'/c mkdir {REMOTE_PATH}')
run_on_dut("cmd.exe", f'/c mkdir {REMOTE_PATH}\\Plugins')

# Step 4: Upload Gambit.App content to DUT
if content_dir:
    print("\nStep 4: Uploading Gambit.App to DUT...")
    for root, dirs, files in os.walk(content_dir):
        for fname in files:
            local_file = os.path.join(root, fname)
            rel_path = os.path.relpath(local_file, content_dir)
            remote_file = f"{REMOTE_PATH}\\{rel_path}"
            # Create remote dir
            remote_dir = os.path.dirname(remote_file)
            run_on_dut("cmd.exe", f'/c if not exist "{remote_dir}" mkdir "{remote_dir}" 2>nul')
            # Upload
            status = upload_file(local_file, remote_file)
            if status != 200:
                print(f"    FAILED to upload {rel_path}: {status}")
    print(f"  Uploaded Gambit.App")

# Step 5: Upload plugins to DUT
print("\nStep 5: Uploading plugins...")
for plugin in PLUGINS:
    pkg_dirs = sorted(glob.glob(os.path.join(plugin_dl, f"{plugin}*")))
    if not pkg_dirs:
        print(f"  {plugin}: not downloaded, skipping")
        continue

    pkg_dir = pkg_dirs[-1]
    plugin_remote = f"{REMOTE_PATH}\\Plugins\\{plugin}"
    run_on_dut("cmd.exe", f'/c mkdir "{plugin_remote}" 2>nul')

    # Find DLLs
    dlls = glob.glob(os.path.join(pkg_dir, "**", "*.dll"), recursive=True)
    if not dlls:
        print(f"  {plugin}: no DLLs found")
        continue

    for dll_path in dlls:
        fname = os.path.basename(dll_path)
        remote_file = f"{plugin_remote}\\{fname}"
        status = upload_file(dll_path, remote_file)

    print(f"  {plugin}: uploaded {len(dlls)} DLLs")

# Step 6: Firewall + verify
print("\nStep 6: Firewall + verify...")
run_on_dut("cmd.exe", f'/c netsh advfirewall firewall add rule name=GambitNew dir=in action=allow program={REMOTE_PATH}\\Gambit.exe protocol=tcp 2>nul')

out, _, _ = run_on_dut("cmd.exe", f'/c dir {REMOTE_PATH} /b')
print(f"  C:\\gambit: {out.strip()}")
out, _, _ = run_on_dut("cmd.exe", f'/c dir {REMOTE_PATH}\\Plugins /b /ad 2>nul')
print(f"  Plugins: {out.strip()}")

print(f"\n{'='*60}")
print(f"  DONE! To start new Gambit with plugins:")
print(f"  On DUT: taskkill /f /im Gambit.exe")
print(f"          {REMOTE_PATH}\\Gambit.exe")
print(f"{'='*60}")
