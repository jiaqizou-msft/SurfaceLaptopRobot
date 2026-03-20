"""Check Gambit plugins on DUT."""
import httpx

BASE = "http://192.168.0.4:22133"
GAMBIT_PATH = r"C:\Users\jiaqizou\OneDrive - Microsoft\Desktop\NewGambit\App"

def run(args, timeout=15):
    r = httpx.post(f"{BASE}/Process/run", json={"Binary": "cmd.exe", "Args": args}, timeout=timeout)
    return r.json().get("Output", "")

print("Gambit directory:")
print(run(f'/c dir "{GAMBIT_PATH}" /b'))

print("\nPlugins subdirectories:")
print(run(f'/c dir "{GAMBIT_PATH}\\Plugins" /b /ad 2>nul'))

print("\nPlugin DLLs:")
print(run(f'/c dir "{GAMBIT_PATH}\\Plugins" /s /b *.Plugin.*.dll 2>nul', timeout=20))

# Check if nuget is available for installing plugins
print("\nnuget available?")
print(run("/c where nuget 2>nul"))
print(run("/c where dotnet 2>nul"))
