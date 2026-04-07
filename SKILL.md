---
description: "Control dual myCobot 280 robot arms to physically interact with a Surface laptop — press keyboard keys, type text, swipe/tap touchpad, open/close lid, dance, and verify via Gambit HID stream. Supports drag-teach recording, iterative calibration, multi-camera GIF capture, and autonomous agent planning. IMPORTANT: Decompose complex requests into sequential tool calls."
applyTo: "**"
tools:
  - keyboard_press_key
  - keyboard_type_text
  - touchpad_swipe
  - touchpad_tap
  - robot_home
  - robot_power_on
  - robot_send_coords
  - robot_send_angles
  - robot_get_status
  - robot_finger_touch
  - robot_set_led
  - robot_head_shake
  - robot_head_nod
  - robot_head_dance
  - robot_stop
  - realsense_capture
  - camera_capture
  - vlm_ask_question
  - agent_execute
  - record_action
---

# Surface Laptop Robot — Physical Device Interaction Skill

Dual **myCobot 280 Pi** robot arms physically interact with a Surface laptop keyboard, touchpad, and lid.

## Architecture Overview

See [visualizations/architecture.png](visualizations/architecture.png) for the full diagram.

```
Windows PC ──TCP JSON :9000──► Pi (robot_cache_server.py) ──Serial──► myCobot 280
                                  └─ 10Hz angle cache (works with released servos)

Surface Laptop (DUT) ──Gambit API :22133──► /streams/keyboard (HID verify)
                                           /streams/cursor   (touchpad verify)
```

### Hardware

| Component | Address | Role |
|-----------|---------|------|
| Right arm Pi | 192.168.0.5:9000 | Keyboard right-half, lid open/close, touchpad right half |
| Left arm Pi | 192.168.0.6:9000 | Keyboard left-half, touchpad left half, lid close |
| DUT (Surface) | 192.168.0.4:22133 | Gambit API for HID verification |
| SSH creds | er / Elephant | Both Pis |

### New Laptop Setup

**Step 1: Network** — The controlling laptop must be on the same subnet as the Pis (192.168.0.x). If Ethernet shows a 169.254.x.x address (no DHCP), set a static IP:
```
netsh interface ip set address "Ethernet" static 192.168.0.10 255.255.255.0
```

**Step 2: Verify connectivity** — Scan for the Pis:
```python
python -c "
import socket, concurrent.futures
def check(ip):
    for port in [9000, 22]:
        try:
            s = socket.socket(); s.settimeout(1); s.connect((ip, port)); s.close(); return ip, port
        except: pass
    return None
ips = [f'192.168.0.{i}' for i in range(1, 255)]
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
    for r in ex.map(check, ips):
        if r: print(f'  {r[0]}: port {r[1]}')
"
```
Expected: `192.168.0.5: port 9000` and `192.168.0.6: port 9000`

**Step 3: Install dependencies** — `pip install -r requirements.txt`

**Step 4: Test connection**:
```python
import sys; sys.path.insert(0, '.')
from src.cobot.cached_robot import CachedRobot
mc_r = CachedRobot('192.168.0.5', 9000)
mc_l = CachedRobot('192.168.0.6', 9000)
mc_r.power_on(); mc_l.power_on()
print('Right:', mc_r.ping())  # expect True
print('Left:', mc_l.ping())   # expect True
```

**Step 5: If cache server not running** — SSH into each Pi and start it:
```bash
ssh er@192.168.0.5  # password: Elephant
cd /home/er
python3 robot_cache_server.py &
```
Or deploy from the laptop: `python scripts/deploy/deploy_cache_server.py`

### Communication Stack

```
CachedRobot (src/cobot/cached_robot.py)
    │  JSON-over-TCP, newline-delimited
    ▼
robot_cache_server.py (on each Pi)
    │  pymycobot direct serial, 10Hz cache poller
    ▼
myCobot 280 (/dev/ttyAMA0 @ 1M baud)
```

**Key commands**: `get_angles` (cached, instant), `send_angles`, `send_coords`, `release` (free servos), `focus` (lock servos), `color`, `power_on`, `ping`.

**Why caching**: `get_angles()` returns -1 when servos are released via the old TCP bridge. The cache server reads angles locally at 10Hz, caches the last valid reading, and serves it to any TCP client — instant, 100% reliable, even with released servos.

### Data Files

| File | Purpose |
|------|---------|
| `data/keyboard_taught.json` | 78 manually drag-taught key positions |
| `data/learned_corrections.json` | 32 per-key Gambit-verified offset corrections |
| `data/taught_actions.json` | Lid open/close dual-arm trajectories |
| `data/keyboard_layout_xml.json` | CAD mm positions from Ortler XML |
| `data/touchpad_boundaries.json` | Taught touchpad 4-corner positions per arm |
| `data/camera_map.json` | USB camera index → role mapping |
| `data/calibration_data.json` | Affine transforms (pixel → robot XY) |

### Gambit Integration

Gambit runs on the DUT and provides HID-level verification:

- **Keyboard stream**: `GET /streams/keyboard` → `{"Key":"A","IsPressed":true}`
  - VK names are PascalCase: `Space`, `Oemcomma`, `Oem1`
  - Single-consumer — must restart Gambit between stream sessions
- **Cursor stream**: `GET /streams/cursor/current` → `{"X":681,"Y":505}`
- **Process run**: `POST /Process/run` — execute commands on DUT

### Camera System

| Camera | Role | Notes |
|--------|------|-------|
| Index 1 | Overhead | Flipped 180°, top-down keyboard view |
| Index 2 | Front | Front workspace, both arms visible |

Camera indices may shift on different laptops. Use `cv2.CAP_DSHOW` on Windows. The overhead camera (index 1) must be flipped with `cv2.flip(frame, -1)`.

---

## CRITICAL: Action Planning

**Decompose every user request into atomic tool calls.** Each tool = ONE action.

| User says | You call (in order) |
|-----------|-------------------|
| "swipe up and down" | `touchpad_swipe("up")` → `touchpad_swipe("down")` |
| "type hello then scroll" | `keyboard_type_text("hello")` → `touchpad_swipe("down")` |
| "open and close lid 5 times" | Replay `open_lid` → `close_lid` × 5 |
| "press A, B, C" | `keyboard_press_key("a")` → `"b"` → `"c"` |

### Planning rules

- **"and"** = multiple actions, call each separately
- **"then"** = sequential order
- **"X times"** = repeat N times
- **"a few"** = 3, **"several"** = 5, **"many"** = 10
- Call `robot_home()` after multi-step sequences

---

## Available Tools

### Keyboard

| Tool | Args | Description |
|------|------|-------------|
| `keyboard_type_text(text, speed)` | text: string, speed: slow/medium/fast | Type a character string |
| `keyboard_press_key(key)` | key: a-z, 0-9, esc, tab, space, enter | Press single key |

**Typing script**: `python scripts/gambit/type_text.py "text to type"`

**Arm assignments** (avoids center-column collisions):
- Left arm (192.168.0.6): `` ` 1 2 3 4 5 6 Q W E R T Y A S D F G H Caps Tab Shift_L Ctrl_L Fn Win Alt_L Z X C V B ``
- Right arm (192.168.0.5): `` 7 8 9 0 - = U I O P [ ] \ J K L ; ' Enter N M , . / Shift_R ``
- H and Y are on the **left arm** to avoid collision in the center column

**Key press standards**:
- **Short press (default)**: 100ms contact time — press down, sleep 100ms, lift immediately
- **Long press / hold**: Not yet implemented — will be a separate skill when needed
- Key repeat = press held too long. Keep contact at 100ms to avoid repeats.

### Key Press Timing

| Press Type | Contact Duration | Use Case |
|------------|-----------------|----------|
| **Short press** | ~100ms | Standard character/number input (default) |
| **Long press** | >500ms | Not implemented yet — future skill |

The typing script uses a two-stage tap: hover → low hover (8mm) → strike at speed 80 → lift. This ensures contact is ~100ms to avoid key repeats.

**Typing script**: `python scripts/gambit/type_text.py "text to type"`

**Collision avoidance**: For center keys (6, 7, Y, U, G, H, B, N, T, J), the other arm nudges sideways 30mm instead of full retract.

**Concurrency**: While one arm presses, the other arm pre-positions to its next key for faster overall typing speed.

**Arm assignments** (to avoid center-column collisions):
- Left arm (31 keys): \` 1-6, Q W E R T Y, A S D F G H, Z X C V B, Caps, Tab, Shift_L, Ctrl_L, Fn, Win, Alt_L
- Right arm (47 keys): 7-0, U I O P, J K L, N M, and all keys right of center

**Calibration**:
- `python scripts/gambit/quick_recalibrate.py` — teach 3 left + 4 right anchors, affine fit to XML layout
- `python annotate_keys.py` — visual annotation GUI, click 2+ keys on overhead image
- `python scripts/gambit/vision_to_robot.py` — convert annotated pixel positions to robot coords
- Anchor keys: Left = Q, Z, 6 | Right = P, /, 9, N
- All positions stored in `data/keyboard_taught.json` (78 keys)
- Z height: ~47mm for both arms (same end effector)

**Network**: Right arm = 192.168.0.5, Left arm = 192.168.0.6 (cache server on port 9000)

**Cameras**: Camera 1 = overhead (flipped), Camera 2 = front view

### Touchpad

The touchpad is split between both arms: **left arm covers the left half**, **right arm covers the right half**.

| Tool | Args | Description |
|------|------|-------------|
| `touchpad_left_click()` | — | Left click (left arm, center of left half, press 6mm below surface) |
| `touchpad_right_click()` | — | Right click (right arm, bottom-right corner, press 6mm below surface) |
| `touchpad_scroll_up()` | — | Two-finger scroll up (both arms, light surface contact, slide 25mm toward keyboard) |
| `touchpad_scroll_down()` | — | Two-finger scroll down (both arms, reverse of scroll up) |
| `touchpad_swipe(direction)` | up/down/left/right | Single-finger cursor swipe |
| `touchpad_swipe(direction, arm)` | direction + left/right | Single-finger swipe with specific arm |
| `touchpad_tap(x_frac, y_frac)` | 0.0-1.0 each | Tap at fractional position |

**Click zones** (from XML: touchpad offset X=80 Y=120, size 111×90mm):
```
┌─────────────┬─────────────┐
│  LEFT ARM   │  RIGHT ARM  │
│  (left clk) │  (left clk) │
├─────────────┼─────────────┤
│  LEFT ARM   │░░RIGHT ARM░░│
│  (left clk) │░(RIGHT clk)░│
└─────────────┴─────────────┘
```
Only the **bottom-right quadrant** triggers right-click. Everything else is left-click.

**Gesture parameters** (tuned for Surface Laptop touchpad):

| Parameter | Value | Notes |
|-----------|-------|-------|
| Click press depth | 6mm below surface | Firm press (~150g force to register) |
| Click contact time | 200ms | Hold briefly then lift |
| Hover offset | 25mm above surface | Approach height |
| Scroll/swipe contact Z (left) | Surface + 9.5mm | Light touch, no click |
| Scroll/swipe contact Z (right) | Surface + 4.5mm | Light touch, no click |
| Scroll/swipe distance | 25mm | Slide distance per gesture |
| Scroll/swipe slide speed | 8 (slow) | Slow enough for touchpad to register |
| Scroll/swipe approach speed | 15 | Touch down speed |
| Right arm keyboard Z | 54.5mm | Right finger is longer than left |
| Left arm keyboard Z | 47.7mm | Standard surface height |

**Scroll mechanics**:
- Both arms touch near the **center dividing line** of the touchpad
- Contact is **above** surface level — **no downward press** (avoids triggering click)
- Arms are mirrored: "up" is opposite Y direction for each arm
- Taught scroll start positions: Left (254.9, -51.8), Right (244.4, 27.3)
- Taught scroll orientations: Left (174.52, 1.9, -109.66), Right (-177.32, 4.08, 16.25)
- Scroll up = slide from taught position toward top edge
- Scroll down = start near top, slide back to taught position

**Single-finger swipe mechanics**:
- Used for **cursor movement** (not scrolling)
- Only one arm moves at a time — the **other arm must be parked home** to avoid collision
- Direction is computed from touchpad corner geometry:
  - **Up/Down**: along the top-left↔bottom-left axis (left arm) or top-right↔bottom-right axis (right arm)
  - **Left/Right**: perpendicular to up/down axis
- Same contact Z and slide speed as scroll (surface contact, speed 8, 25mm distance)
- Left arm contact Z: surface + 9.5mm | Right arm contact Z: surface + 4.5mm

**Right click targeting**: Uses the exact taught bottom-right corner position and orientation from `data/touchpad_boundaries.json`.

**Arm orientations**: Each arm uses its own taught orientation (rx, ry, rz) from boundary teaching. Orientations must use angle-safe averaging (atan2) to avoid ±180° wrapping bugs.

**Test script**: `python scripts/gambit/test_touchpad_gestures.py`

**Boundary teaching**: `python scripts/gambit/teach_touchpad_bounds.py` — teaches 4 corners (left arm: TL+BL, right arm: TR+BR), saves to `data/touchpad_boundaries.json`

### Device Unlock

Unlock the Surface Laptop from lock screen by pressing keys:

1. Press **SPACE** to dismiss the lock screen and enter PIN mode
2. Type PIN: **kbtp123**
3. Press **ENTER** to submit
4. Wait ~4s for login to complete
5. Capture before/after camera images to verify unlock

**Collision avoidance**: PIN digits use both arms concurrently (1, 5 = left; 9, 8 = right).

**Demo script**: `python scripts/gambit/demo_full.py` (phase 2) or inline.

### Lid Actions

Taught trajectories stored in `data/taught_actions.json`.

| Action | Method | Description |
|--------|--------|-------------|
| `close_lid` | Sequential: right preps → left closes | Right arm moves between lids first, then left arm pushes lid closed |
| `open_lid` | Both arms together | Both arms work together to open the lid |

**Close lid sequence**:
1. Right arm preps (finger between lids to prevent full close) — 28 waypoints
2. Left arm closes the lid (right stays locked) — 23 waypoints

**Open lid**: Both arms move simultaneously — 22 waypoints

**Replay code pattern**:
```python
from src.cobot.cached_robot import CachedRobot
import json, time

with open('data/taught_actions.json') as f:
    actions = json.load(f)

mc_r = CachedRobot('192.168.0.5', 9000)
mc_l = CachedRobot('192.168.0.6', 9000)
mc_r.power_on(); mc_l.power_on()
time.sleep(1)

# Close: phase-aware replay
a = actions['close_lid']
for wr in a['phases'][0]['right_waypoints']:  # right preps
    mc_r.send_angles(wr, 40); time.sleep(0.2)
time.sleep(1)
for wl in a['phases'][1]['left_waypoints']:   # left closes
    mc_l.send_angles(wl, 40); time.sleep(0.2)
time.sleep(1)

# Open: both arms together
a = actions['open_lid']
for wr, wl in zip(a['right_waypoints'], a['left_waypoints']):
    mc_r.send_angles(wr, 40)
    mc_l.send_angles(wl, 40)
    time.sleep(0.2)
```

**Teaching**: `python scripts/gambit/teach_lid_sequential.py` — teaches close (right prep + left close) and open (both arms) with continuous drag recording.

**Demo script**: `python scripts/gambit/demo_lid.py [cycles]` — runs N cycles with multi-camera GIF recording.

### Robot Motion

| Tool | Description |
|------|-------------|
| `robot_home()` | Return arm to [0,0,0,0,0,0] |
| `robot_send_coords(coords, speed)` | Move to [x,y,z,rx,ry,rz] |
| `robot_send_angles(angles, speed)` | Move to joint angles |
| `robot_finger_touch(x, y)` | Touch workspace point |
| `robot_stop()` | Emergency stop |

### Gestures & LED

| Tool | Description |
|------|-------------|
| `robot_head_shake()` | Shake (no) |
| `robot_head_nod()` | Nod (yes) |
| `robot_head_dance()` | Dance animation |
| `robot_set_led(r, g, b)` | LED color 0-255 |

### Vision

| Tool | Description |
|------|-------------|
| `realsense_capture()` | Overhead RGBD image |
| `camera_capture()` | Side-view image |
| `vlm_ask_question(question)` | GPT-4o visual Q&A |

### Recording

| Tool | Description |
|------|-------------|
| `record_action(action, args)` | Execute action with multi-camera GIF recording |

Supported: `"type <text>"`, `"press <key>"`, `"swipe <dir>"`, `"tap"`, `"dance"`, `"shake"`, `"nod"`

---

## Key Scripts

### Teaching & Calibration

| Script | Purpose |
|--------|---------|
| `scripts/gambit/teach_lid.py` | Drag-teach lid open/close (CachedRobot, continuous recording) |
| `scripts/gambit/teach_touchpad.py` | Teach touchpad center via cursor stream |
| `scripts/gambit/teach_touchpad_bounds.py` | Teach touchpad 4 corners (left/right arms) |
| `scripts/gambit/test_touchpad_gestures.py` | Test left/right click + scroll up/down |
| `scripts/gambit/anchor_calibrate.py` | 3-anchor teach → affine → stream verify |
| `scripts/gambit/stream_calibrate.py` | Per-key Gambit stream verification |
| `scripts/gambit/quick_calibrate.py` | Fast all-key calibration |
| `scripts/calibration/teach_keyboard.py` | Manual drag-teach single arm |
| `scripts/calibration/teach_dual_arm.py` | Manual drag-teach both arms |

### Demos

| Script | Purpose |
|--------|---------|| `scripts/gambit/demo_showcase_loop.py` | Continuous loop: type words + touchpad gestures |
| `scripts/gambit/demo_full.py` | Full demo: lid, login, type, touchpad (separate GIFs) |
| `scripts/gambit/demo_lid.py [cycles]` | Lid close/open with GIF recording |
| `scripts/gambit/live_camera_feed.py` | Live dual-camera window (press q to quit) || `scripts/gambit/type_demo.py` | Type strings with 3-camera GIF + stream verify |
| `scripts/gambit/robot_dance.py` | Dual-arm synchronized dance with GIF |

### Deployment

| Script | Purpose |
|--------|---------|
| `scripts/deploy/deploy_cache_server.py` | Deploy robot_cache_server.py to both Pis |
| `scripts/deploy/restart_bridges.py` | Restart old TCP bridges (fallback) |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection timeout to Pi | Check Pi is powered on, Ethernet connected. Set static IP if needed: `netsh interface ip set address "Ethernet" static 192.168.0.10 255.255.255.0` |
| Pi on wrong subnet (169.254.x.x) | No DHCP server — need a router or static IPs on both PC and Pi |
| Cache server not running (port 9000 closed but SSH port 22 open) | SSH in and run `python3 robot_cache_server.py &` |
| `get_angles()` returns -1 | Cache server not running; redeploy |
| Gambit stream "unable to add consumer" | Restart Gambit: `GET /installer/restart` |
| Camera index shifted on new laptop | Try indices 0-5 with `cv2.VideoCapture(i, cv2.CAP_DSHOW)` |
| Key misses in stream | Clear events before press, wait 1s after release |
| Left arm unreachable | Check dhcpcd.conf static IP on Pi |
| Arms collide during single-finger swipe | Park idle arm home first |

## Workspace Constants

- **Key pitch**: 19mm horizontal, 18.5mm row pitch
- **Hover Z**: 145mm, **Press Z**: 142mm, **Safe Z**: 200mm
- **Touchpad offset**: (80mm, 120mm) from keyboard origin, size 111×90mm
- **Touchpad click depth**: 6mm below surface, **Scroll contact**: surface + 9.5mm (left) / surface + 4.5mm (right)
- **Keyboard Z heights**: Left arm 47.7mm, Right arm 54.5mm (right finger is longer)
- **Joint limits**: J1 ±168°, J2 ±135°, J3 ±150°, J4 ±145°, J5 ±160°, J6 ±180°

## MCP Server Configuration

Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "mycobot": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "C:\\Users\\jiaqizou\\MyCobotAgent"
    }
  }
}
```
