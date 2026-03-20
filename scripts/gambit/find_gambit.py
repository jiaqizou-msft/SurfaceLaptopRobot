"""Find Gambit.exe path on the DUT."""
import httpx

BASE = "http://192.168.0.4:22133"

def run(cmd, args, timeout=15):
    r = httpx.post(f"{BASE}/Process/run", json={"Binary": cmd, "Args": args}, timeout=timeout)
    return r.json().get("Output", "")

# Method 1: tasklist
print("Tasklist:")
print(run("cmd.exe", '/c tasklist /fi "imagename eq Gambit.exe" /fo csv 2>nul'))

# Method 2: wmic
print("\nWMIC:")
print(run("cmd.exe", "/c wmic process where \"name='Gambit.exe'\" get ProcessId,ExecutablePath /format:list 2>nul"))

# Method 3: search common locations
print("\nSearching:")
for p in ["C:\\gambit", "C:\\Gambit", "C:\\Tools\\Gambit", "C:\\Program Files\\Gambit",
          "C:\\Users\\Admin\\Gambit", "C:\\Users\\jiaqizou\\Gambit"]:
    out = run("cmd.exe", f'/c if exist "{p}\\Gambit.exe" echo FOUND:{p}')
    if "FOUND" in out:
        print(f"  {out.strip()}")
        # List plugins
        pout = run("cmd.exe", f'/c dir "{p}\\Plugins" /b /ad 2>nul')
        print(f"  Plugins: {pout.strip() if pout.strip() else 'none'}")

# Method 4: where /r to find it
print("\nSearching C:\\ (may take a moment):")
print(run("cmd.exe", "/c where /r C:\\ Gambit.exe 2>nul", timeout=30))
