# Auditoria vs NitroSense Windows (ANV15-51)

Referência: manual Nitro V 15 (Home, Scenario, Fan Auto/Max/Custom, Monitoring 30–60 min, tecla dedicada).

| Função Windows | Aqui | Estado |
|---|---|---|
| Tecla N abre a app | `KEY_PROG1` (148) → XF86Launch1 + listener sem grab | **ligado** |
| Instância única / foca se já aberta | Gtk `org.alfred.nitrosense` | **sim** |
| Temps CPU/GPU | coretemp + nvidia-smi | **sim** |
| Load CPU/GPU (anel) | `/proc/stat` + nvidia-smi | **sim** |
| RPM fans | sysfs hwmon acer | **sim (Linuwu)** |
| Quiet / Default / Performance | platform_profile | **sim; firmware recusa Turbo** |
| Fan Auto / Max / Custom | `fan_speed` (`0,0` / `100,100` / `cpu,gpu`) | **sim** |
| Limite carga 80%, calibração, USB charging | sysfs nitro_sense | **sim** |
| Backlight timeout | sysfs | **sim; teclado 1 cor neste chassis** |
| RAM | MemTotal − MemAvailable | **HOME rodapé + MONITORING** |
| RGB 4 zonas | four_zoned_kb | **N/A neste ANV15-51** |
| Monitoring 30 min | sparklines 1800 pts | **sim (sem 3D)** |
| Avatar 3D Acer | silhueta cairo | **aproximação** |
| Scenario profiles ligados a apps | — | **não** |
| App Center / Planet9 | — | **não** |
| CoolBoost / Optimus toggle | — | **não (nem todos os Nitro V têm)** |
| Driver WMI (fans/modos de verdade) | Linuwu Sense | **módulo `linuwu_sense`** |

Aparência: HUD preto + laranja, anéis, Quiet/Default/Performance, Auto/Max/Custom — alinhado ao Windows. Sem assets 3D da Acer.
