# NitroSense Linux

**Unofficial** NitroSense clone for Acer Nitro on Linux. Tested on **ANV15-51**.
Not affiliated with Acer. GTK4 HUD; same firmware. Fans, power profiles and battery
go through [Linuwu Sense](https://github.com/PXDiv/Div-Linuwu-Sense) (the same engine
DAMX already covers on this model).

System monitoring matches the GNOME **Resources** app you already run
(`net.nokyan.Resources`): CPU cores, memory, swap, GPU, default-route NIC, disks,
battery, and a process list with End.

## Install (.deb)

Each merge into `main` publishes a [Release](https://github.com/rodriguesfas/nitrosense/releases)
with tag `vX.Y.Z` and `nitrosense_X.Y.Z_all.deb`.

```bash
sudo apt install ./nitrosense_*_all.deb
nitrosense                 # GUI
nitrosense-setup           # Linuwu driver (fans, profile, battery) — asks for sudo
```

The `.deb` ships the app. The kernel module is **not** in the package (it depends on
your kernel). After the driver, log out and back in (`linuwu_sense` group).

## Run from source

```bash
git clone https://github.com/rodriguesfas/nitrosense.git
cd nitrosense
./bin/nitrosense
./install-hotkey.sh        # N key (KEY_PROG1 → XF86Launch1)
./setup.sh                 # Linuwu driver
```

GUI dependencies: `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`.

## What it covers

| NitroSense / Resources | Here |
|---|---|
| CPU / GPU temps and load | HOME rings |
| Per-core CPU | RESOURCES — sparkline cards per CPU, logical/physical toggle |
| RAM used / total | HOME footer + MONITORING |
| SWAP used / total | HOME footer + MONITORING |
| Default-route NIC (↓/↑ Mb/s, IPv4) | HOME footer + RESOURCES |
| Disk usage and I/O | HOME footer + MONITORING + RESOURCES |
| Processes (filter, End / SIGTERM) | RESOURCES |
| Battery %, power, AC | header chip + RESOURCES + SETTINGS |
| Fan RPM | HOME, after the driver |
| Quiet / Default / Performance | ACPI profiles. Turbo **does not exist** on this chassis (firmware rejects it) |
| Auto / Max / Custom fans | HOME and SCENARIO — Custom writes `cpu%,gpu%` to Linuwu sysfs |
| Scenario per-app profiles | SCENARIO — persist `~/.config/nitrosense/scenarios.json`; each rule binds Quiet/Default/Performance **and** Auto/Max/Custom fans |
| 80% charge limit, calibration, USB charging | SETTINGS |
| RTX TGP Default / Boost | SETTINGS — `nvidia-smi` (60 W vs 75 W on this RTX 4050). Needs pkexec once; resets at reboot |
| Backlight timeout, display brightness, Night Light | LIGHTING |
| 4-zone RGB | Only if `four_zoned_kb` appears in sysfs. ANV15-51 is a **single-color** backlight |
| N key | `KEY_PROG1` (Acer WMI) → XF86Launch1 + grab-free listener |

NPU pages from Resources stay hidden unless the kernel exposes an NPU (this i5-13420H does not).

## Branches

| Branch | Use |
|---|---|
| `dev` | Day-to-day work |
| `main` | Stable. Push/merge here creates tag `v$(cat VERSION)` and the `.deb` |

Bump `VERSION` before merging `dev` → `main`. The workflow refuses to reuse an existing tag.

## Tree

```
nitrosense/     GUI + hardware + sensors
bin/            launcher, hotkey, pkexec helper, fixperms
packaging/      build-deb.sh
.github/        .deb release on main
setup.sh        Linuwu driver
```

Windows parity notes: [AUDIT.md](AUDIT.md).
