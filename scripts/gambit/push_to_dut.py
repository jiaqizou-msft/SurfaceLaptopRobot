"""Push already-downloaded Gambit + plugins to C:\\gambit on the DUT."""
import httpx
import os
import glob
import time

BASE = "http://192.168.0.4:22133"
REMOTE_PATH = "C:\\gambit"
LOCAL_STAGING = "C:\\Staging\\GambitDeploy"

def run(cmd, args, timeout=30):
    r = httpx.post(f"{BASE}/Process/run", json={"Binary": cmd, "Args": args}, timeout=timeout)
    data = r.json()
    return data.get("Output", ""), data.get("Error", ""), data.get("ExitCode", -1)

def upload_file(local_path, remote_path):
    with open(local_path, "rb") as f:
        r = httpx.post(f"{BASE}/file/upload", files={"file": (os.path.basename(local_path), f)},
                       params={"path": remote_path}, timeout=120)
    return r.status_code

print("=" * 55)
print("  PUSHING GAMBIT + PLUGINS TO DUT")
print("=" * 55)

# Prepare directories
run("cmd.exe", f'/c if not exist {REMOTE_PATH} mkdir {REMOTE_PATH}')
run("cmd.exe", f'/c if not exist {REMOTE_PATH}\\Plugins mkdir {REMOTE_PATH}\\Plugins')

# Upload Gambit.App content
content_dirs = sorted(glob.glob(os.path.join(LOCAL_STAGING, "downloads", "Gambit.App*")))
if content_dirs:
    content_dir = os.path.join(content_dirs[-1], "content")
    print(f"\nUploading Gambit.App from {content_dir}...")
    count = 0
    for fname in os.listdir(content_dir):
        fpath = os.path.join(content_dir, fname)
        if os.path.isfile(fpath):
            status = upload_file(fpath, f"{REMOTE_PATH}\\{fname}")
            count += 1
            if count % 5 == 0:
                print(f"  {count} files...")
    print(f"  Uploaded {count} Gambit.App files")
else:
    print("  No Gambit.App found locally!")

# Upload plugins
plugins_dir = os.path.join(LOCAL_STAGING, "plugins_dl")
if os.path.exists(plugins_dir):
    plugin_pkgs = sorted(glob.glob(os.path.join(plugins_dir, "Gambit.Plugin*")))
    print(f"\nUploading {len(plugin_pkgs)} plugins...")
    
    for pkg_dir in plugin_pkgs:
        plugin_name = os.path.basename(pkg_dir).rsplit(".", 1)[0]  # remove version
        # Extract just the plugin name (Gambit.Plugin.XXX)
        parts = os.path.basename(pkg_dir).split(".")
        # Find where version numbers start
        name_parts = []
        for p in parts:
            if p.isdigit():
                break
            name_parts.append(p)
        plugin_name = ".".join(name_parts)
        
        remote_plugin = f"{REMOTE_PATH}\\Plugins\\{plugin_name}"
        run("cmd.exe", f'/c if not exist "{remote_plugin}" mkdir "{remote_plugin}"')
        
        # Find DLLs
        dlls = glob.glob(os.path.join(pkg_dir, "**", "*.dll"), recursive=True)
        for dll in dlls:
            fname = os.path.basename(dll)
            upload_file(dll, f"{remote_plugin}\\{fname}")
        
        print(f"  {plugin_name}: {len(dlls)} DLLs")

# Add firewall rule
run("cmd.exe", f'/c netsh advfirewall firewall add rule name=GambitNew dir=in action=allow program={REMOTE_PATH}\\Gambit.exe protocol=tcp 2>nul')

# Verify
print("\nVerifying...")
out, _, _ = run("cmd.exe", f'/c dir {REMOTE_PATH} /b')
print(f"  C:\\gambit: {out.strip()}")
out, _, _ = run("cmd.exe", f'/c dir {REMOTE_PATH}\\Plugins /b /ad 2>nul')
print(f"  Plugins: {out.strip()}")

# Check Gambit.exe exists
out, _, _ = run("cmd.exe", f'/c if exist {REMOTE_PATH}\\Gambit.exe echo YES')
print(f"  Gambit.exe: {out.strip()}")

print(f"\n{'='*55}")
print(f"  DONE! Now restart Gambit from C:\\gambit:")
print(f"  1. Kill old: taskkill /f /im Gambit.exe")
print(f"  2. Start new: C:\\gambit\\Gambit.exe")
print(f"{'='*55}")
