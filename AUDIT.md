# Audit vs Windows NitroSense (ANV15-51)

Reference: Nitro V 15 manual (Home, Scenario, Fan Auto/Max/Custom, Monitoring 30–60 min, dedicated key) plus GNOME Resources 1.10.2 (`net.nokyan.Resources`).

| Windows / Resources feature | Here | Status |
|---|---|---|
| N key opens the app | `KEY_PROG1` (148) → XF86Launch1 + grab-free listener | **on** |
| Single instance / focus if already open | Gtk `org.alfred.nitrosense` | **yes** |
| CPU/GPU temps | coretemp + nvidia-smi | **yes** |
| CPU/GPU load (ring) | `/proc/stat` + nvidia-smi | **yes** |
| Per-core CPU | `/proc/stat` cpuN | **RESOURCES** |
| Fan RPM | acer hwmon sysfs | **yes (Linuwu)** |
| Quiet / Default / Performance | platform_profile | **yes; firmware rejects Turbo** |
| Fan Auto / Max / Custom | `fan_speed` (`0,0` / `100,100` / `cpu,gpu`) | **yes** |
| 80% charge limit, calibration, USB charging | nitro_sense sysfs | **yes** |
| Backlight timeout | sysfs | **yes; single-color keyboard on this chassis** |
| RAM | MemTotal − MemAvailable | **HOME footer + MONITORING** |
| SWAP | SwapTotal − SwapFree | **HOME footer + MONITORING** |
| Network | `/proc/net/dev` on the default route + IPv4 | **HOME footer + MONITORING + RESOURCES** |
| Disks | `/proc/diskstats` + `statvfs` | **HOME footer + MONITORING + RESOURCES** |
| Processes + End | `/proc/[pid]` + SIGTERM | **RESOURCES** |
| Battery | power_supply sysfs | **header + RESOURCES + SETTINGS** |
| 4-zone RGB | four_zoned_kb | **N/A on this ANV15-51** |
| 30 min monitoring | 1800-point sparklines | **yes (no 3D)** |
| Acer 3D avatar | cairo silhouette | **approximation** |
| Scenario profiles bound to apps | — | **no** |
| App Center / Planet9 | — | **no** |
| CoolBoost / Optimus toggle | — | **no (not every Nitro V has them)** |
| NPU | — | **hidden unless the kernel exposes one** |
| WMI driver (real fans/modes) | Linuwu Sense | **`linuwu_sense` module** |

Look: black + orange HUD, rings, Quiet/Default/Performance, Auto/Max/Custom — aligned with Windows. No Acer 3D assets.
