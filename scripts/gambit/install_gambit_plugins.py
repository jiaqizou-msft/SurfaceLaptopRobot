"""Install Gambit + all plugins on the DUT from NuGet feed via Gambit's Process API."""
import httpx
import time

BASE = "http://192.168.0.4:22133"
NUGET_SOURCE = "https://pkgs.dev.azure.com/MSFTDEVICES/_packaging/Shared/nuget/v3/index.json"
GAMBIT_PATH = "C:\\gambit"

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

def run(cmd, args, timeout=120):
    r = httpx.post(f"{BASE}/Process/run", json={"Binary": cmd, "Args": args}, timeout=timeout)
    data = r.json()
    out = data.get("Output", "")
    err = data.get("Error", "")
    code = data.get("ExitCode", -1)
    return out, err, code

print("=" * 60)
print("  INSTALLING GAMBIT + PLUGINS ON DUT")
print("=" * 60)

# Step 1: Install nuget CLI if not available
print("\nStep 1: Check/install nuget...")
out, _, _ = run("cmd.exe", "/c where nuget 2>nul")
if "nuget" not in out.lower():
    print("  nuget not found. Downloading nuget.exe...")
    out, err, code = run("cmd.exe",
        '/c curl -o C:\\nuget.exe https://dist.nuget.org/win-x86-commandline/latest/nuget.exe 2>nul',
        timeout=60)
    print(f"  Download: exit={code}")
    nuget = "C:\\nuget.exe"
else:
    nuget = out.strip().split("\n")[0].strip()
    print(f"  nuget found: {nuget}")

# Step 2: Create gambit directory
print("\nStep 2: Preparing C:\\gambit...")
run("cmd.exe", f'/c if exist {GAMBIT_PATH} rmdir /s /q {GAMBIT_PATH}')
time.sleep(1)
run("cmd.exe", f'/c mkdir {GAMBIT_PATH}')
run("cmd.exe", f'/c mkdir {GAMBIT_PATH}\\Plugins')

# Step 3: Download Gambit.App
print("\nStep 3: Downloading Gambit.App...")
out, err, code = run("cmd.exe",
    f'/c C:\\nuget.exe install Gambit.App -Source "{NUGET_SOURCE}" -OutputDirectory C:\\staging_gambit -PreRelease -NonInteractive 2>&1',
    timeout=180)
print(f"  Exit: {code}")
if "error" in (out + err).lower():
    print(f"  Error: {(out + err)[:300]}")
else:
    print(f"  Output: {out[:200]}")

# Find the content folder
out_find, _, _ = run("cmd.exe", '/c dir C:\\staging_gambit\\Gambit.App* /b /ad 2>nul')
pkg_dir = out_find.strip().split("\n")[0].strip() if out_find.strip() else ""
if pkg_dir:
    content_src = f"C:\\staging_gambit\\{pkg_dir}\\content"
    print(f"  Package: {pkg_dir}")
    
    # Copy to C:\gambit
    print("  Copying to C:\\gambit...")
    out, _, code = run("cmd.exe", f'/c xcopy "{content_src}\\*" "{GAMBIT_PATH}\\" /s /e /y 2>nul')
    print(f"  Copy: exit={code}")
else:
    print("  WARNING: Could not find Gambit.App package!")

# Step 4: Download and install each plugin
print("\nStep 4: Installing plugins...")
for plugin in PLUGINS:
    print(f"\n  Installing {plugin}...")
    
    # Download
    out, err, code = run("cmd.exe",
        f'/c C:\\nuget.exe install {plugin} -Source "{NUGET_SOURCE}" -OutputDirectory C:\\staging_plugins -PreRelease -NonInteractive 2>&1',
        timeout=120)
    
    if code != 0 and "error" in (out + err).lower():
        print(f"    FAILED: {(out+err)[:150]}")
        continue
    
    # Find the downloaded package
    out_find, _, _ = run("cmd.exe", f'/c dir C:\\staging_plugins\\{plugin}* /b /ad /o-n 2>nul')
    pkg = out_find.strip().split("\n")[0].strip() if out_find.strip() else ""
    if not pkg:
        print(f"    Package not found after download")
        continue
    
    # Create plugin folder
    plugin_dest = f"{GAMBIT_PATH}\\Plugins\\{plugin}"
    run("cmd.exe", f'/c mkdir "{plugin_dest}" 2>nul')
    
    # Find DLLs - look for net8 or lib folder
    out_dlls, _, _ = run("cmd.exe", f'/c dir "C:\\staging_plugins\\{pkg}" /s /b *.dll 2>nul')
    if out_dlls.strip():
        # Copy all DLLs to plugin folder
        dlls = [d.strip() for d in out_dlls.strip().split("\n") if d.strip()]
        for dll in dlls[:20]:  # limit
            run("cmd.exe", f'/c copy "{dll}" "{plugin_dest}\\" /y 2>nul')
        print(f"    Installed {len(dlls)} DLLs")
    else:
        print(f"    No DLLs found in package")

# Step 5: Add firewall rule
print("\nStep 5: Adding firewall rule...")
run("cmd.exe", f'/c netsh advfirewall firewall add rule name=Gambit dir=in action=allow program={GAMBIT_PATH}\\Gambit.exe protocol=tcp 2>nul')

# Step 6: Verify
print("\nStep 6: Verifying installation...")
out, _, _ = run("cmd.exe", f'/c dir {GAMBIT_PATH} /b')
print(f"  C:\\gambit contents:\n{out}")

out, _, _ = run("cmd.exe", f'/c dir {GAMBIT_PATH}\\Plugins /b /ad 2>nul')
print(f"\n  Plugins:\n{out}")

# Clean up staging
print("\nCleaning up staging...")
run("cmd.exe", "/c rmdir /s /q C:\\staging_gambit 2>nul")
run("cmd.exe", "/c rmdir /s /q C:\\staging_plugins 2>nul")

print(f"\n{'='*60}")
print(f"  INSTALLATION COMPLETE")
print(f"{'='*60}")
print(f"  Gambit installed at: {GAMBIT_PATH}")
print(f"  To start: kill old Gambit, then run {GAMBIT_PATH}\\Gambit.exe")
print(f"  The old running Gambit will need to be stopped first.")
print(f"  Run on DUT: taskkill /f /im Gambit.exe & {GAMBIT_PATH}\\Gambit.exe")
