"""Check what's already on the DUT and install missing plugins via Gambit's Process API."""
import httpx
import json
import time

BASE = "http://192.168.0.4:22133"

def run_on_dut(cmd, args, timeout=30):
    """Run a command on the DUT via Gambit Process/run."""
    body = {"Binary": cmd, "Args": args}
    r = httpx.post(f"{BASE}/Process/run", json=body, timeout=timeout)
    if r.status_code == 200:
        data = r.json()
        return data.get("Output", ""), data.get("Error", ""), data.get("ExitCode", -1)
    return "", f"HTTP {r.status_code}: {r.text[:200]}", -1

print("=" * 55)
print("  DUT PLUGIN CHECK")
print("=" * 55)

# Check if Gambit is in C:\gambit
out, err, code = run_on_dut("cmd.exe", "/c dir C:\\gambit 2>nul")
print(f"\nC:\\gambit contents:")
print(out if out else "  (empty or not found)")

# Check Plugins folder
out, err, code = run_on_dut("cmd.exe", "/c dir C:\\gambit\\Plugins 2>nul")
print(f"\nPlugins folder:")
print(out if out else "  (empty or not found)")

# Check where Gambit.exe is running from
out, err, code = run_on_dut("cmd.exe", "/c wmic process where name='Gambit.exe' get ExecutablePath 2>nul")
print(f"\nGambit.exe location:")
print(out.strip() if out else "  (not found via wmic)")

# Alternative: check common locations
for path in ["C:\\gambit", "C:\\Gambit", "C:\\Program Files\\Gambit"]:
    out, err, code = run_on_dut("cmd.exe", f'/c if exist "{path}\\Gambit.exe" echo FOUND at {path}')
    if "FOUND" in out:
        print(f"  Gambit.exe found at: {path}")
        # Check plugins there
        out2, _, _ = run_on_dut("cmd.exe", f'/c dir "{path}\\Plugins" /b 2>nul')
        if out2:
            print(f"  Plugins: {out2.strip()}")
        break

# Check if nuget is available
out, err, code = run_on_dut("cmd.exe", "/c where nuget 2>nul")
print(f"\nnuget location: {out.strip() if out else 'not found'}")

# Check if we have internet from DUT (for plugin download)
out, err, code = run_on_dut("cmd.exe", "/c ping 8.8.8.8 -n 1 -w 2000 2>nul | findstr Reply")
print(f"Internet: {'YES' if 'Reply' in out else 'NO'}")

print("\nDone!")
