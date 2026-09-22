"""English / Brazilian Portuguese strings for the NitroSense GUI."""

from __future__ import annotations

import json
import os
from pathlib import Path

UI_PATH = Path.home() / ".config/nitrosense/ui.json"
LANGS = ("en", "pt_BR")
LANG_LABELS = ("English", "Português (Brasil)")

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "tab.home": "HOME",
        "tab.scenario": "SCENARIO",
        "tab.monitoring": "MONITORING",
        "tab.resources": "RESOURCES",
        "tab.lighting": "LIGHTING",
        "tab.settings": "SETTINGS",
        "mode.quiet": "Quiet",
        "mode.default": "Default",
        "mode.performance": "Performance",
        "fan.auto": "Auto",
        "fan.max": "Max",
        "fan.custom": "Custom",
        "fan.cpu": "CPU fan",
        "fan.gpu": "GPU fan",
        "scen.intro": "Quiet, Default and Performance plus Auto / Max / Custom fans — same controls as Windows NitroSense. Bind a profile and fan mode to a running app; they apply while that process is open.",
        "scen.now": "Now  {mode}  ·  fans {fan}{extra}",
        "scen.rule_extra": "  ·  rule {name}",
        "scen.rules": "APPLICATION RULES",
        "scen.apply": "Apply automatically",
        "scen.add": "Add",
        "scen.hint": "First matching running process wins. A manual mode or fan click on HOME or here pauses auto-apply for 45 seconds.",
        "scen.empty": "No application rules yet. Pick a running app and Add.",
        "scen.remove": "Remove",
        "scen.running": "running",
        "scen.rule": "{mode}  ·  {fans}",
        "scen.rule_custom": "{mode}  ·  {fans} {cpu}/{gpu}",
        "mon.hint": "Last ~30 minutes (1 Hz). CPU, GPU, RAM, SWAP, network and disk I/O.",
        "res.processor": "PROCESSOR",
        "res.options": "OPTIONS",
        "res.usage": "USAGE",
        "res.memory": "MEMORY",
        "res.graphics": "GRAPHICS",
        "res.network": "NETWORK",
        "res.storage": "STORAGE",
        "res.battery": "BATTERY",
        "res.processes": "PROCESSES",
        "res.logical": "Show logical CPU usage",
        "proc.filter": "Filter processes",
        "proc.name": "NAME",
        "proc.pid": "PID",
        "proc.cpu": "CPU",
        "proc.memory": "MEMORY",
        "proc.end": "End",
        "light.page": "LIGHTING",
        "light.keyboard": "KEYBOARD",
        "light.display": "DISPLAY",
        "light.night_section": "NIGHT LIGHT",
        "light.timeout": "Backlight timeout (30 s idle)",
        "light.timeout_hint": "Click the keyboard or the switch. ANV15-51 is single-color — Fn cycles Off / mid / full.",
        "light.brightness": "Brightness",
        "light.brightness_pct": "Brightness  ·  {pct}%",
        "light.lcd": "LCD override",
        "light.night": "Night Light",
        "light.night_hint": "Warmer screen (GNOME). Temperature in Kelvin.",
        "light.rgb": "Four-zone RGB",
        "light.caps": "CAPS",
        "light.num": "NUM",
        "light.scroll": "SCROLL",
        "set.driver": "DRIVER",
        "set.battery": "BATTERY",
        "set.startup": "STARTUP",
        "set.install": "Install Linuwu driver",
        "set.limit": "Charge limit 80%",
        "set.limit_hint": "Stops charging at 80% to reduce battery wear.",
        "set.usb": "USB charging while off",
        "set.usb_hint": "Charge a phone from this USB port while the laptop is off.",
        "set.calibrate": "Calibration",
        "set.calibrate_btn": "Start battery calibration",
        "set.calibrate_hint": "Full cycle 100→0→100. Keep AC plugged in.",
        "set.calibrate_title": "Calibrate battery?",
        "set.calibrate_body": "Full cycle 100→0→100. Keep AC plugged in.",
        "set.boot": "Boot animation / sound",
        "set.boot_hint": "This chassis has no boot-animation sysfs node.",
        "set.autostart": "Open NitroSense at login",
        "set.autostart_hint": "Starts the window when you log in.",
        "set.hotkey": "Dedicated N key",
        "set.hotkey_hint": "The Acer Nitro key (PROG1) opens or focuses this window.",
        "set.language": "Language",
        "set.language_hint": "English or Brazilian Portuguese. Applied immediately.",
        "set.tgp": "GPU POWER",
        "set.tgp_hint": "RTX laptop TGP via nvidia-smi (not Linuwu). Default and Boost. The last choice is restored at login without a password prompt.",
        "set.tgp_now": "Now {watts} W",
        "set.tgp_default": "Default  ·  {watts} W",
        "set.tgp_boost": "Boost  ·  {watts} W",
        "set.tgp_missing": "No NVIDIA GPU with a readable power limit (nvidia-smi).",
        "set.install_title": "Install driver",
        "set.install_body": "In a terminal:\n\n{setup}\n\nNeeds sudo.",
        "fact.driver": "Driver",
        "fact.firmware": "Firmware",
        "fact.profile": "Profile",
        "fact.choices": "Choices",
        "fact.model": "Model",
        "fact.threads": "Threads",
        "fact.frequency": "Frequency",
        "fact.temperature": "Temperature",
        "fact.used": "Used",
        "fact.available": "Available",
        "fact.cached": "Cached",
        "fact.swap": "Swap",
        "fact.interface": "Interface",
        "fact.type": "Type",
        "fact.ipv4": "IPv4",
        "fact.link": "Link",
        "fact.status": "Status",
        "fact.power": "Power",
        "fact.energy": "Energy",
        "fact.cycles": "Cycles",
        "tile.ram": "RAM",
        "tile.swap": "SWAP",
        "tile.net": "NET",
        "tile.disk": "DISK",
        "tile.memory": "Memory",
        "tile.download": "Download",
        "tile.upload": "Upload",
        "tile.charge": "Charge",
        "tile.power": "Power",
        "tile.total": "Total",
        "chart.cpu_temp": "CPU temperature",
        "chart.gpu_temp": "GPU temperature",
        "chart.cpu_load": "CPU loading",
        "chart.gpu_load": "GPU loading",
        "chart.ram_load": "RAM loading",
        "chart.ram_used": "RAM used",
        "chart.swap_load": "SWAP loading",
        "chart.swap_used": "SWAP used",
        "chart.net_down": "Network down",
        "chart.net_up": "Network up",
        "chart.disk_read": "Disk read",
        "chart.disk_write": "Disk write",
        "usb.off": "Off",
        "usb.until": "Until {pct}%",
        "ok": "OK",
        "cancel": "Cancel",
        "start": "Start",
        "swap.off": "SWAP  ·  off",
        "off": "off",
    },
    "pt_BR": {
        "tab.home": "INÍCIO",
        "tab.scenario": "CENÁRIO",
        "tab.monitoring": "MONITOR",
        "tab.resources": "RECURSOS",
        "tab.lighting": "ILUMINAÇÃO",
        "tab.settings": "AJUSTES",
        "mode.quiet": "Silencioso",
        "mode.default": "Padrão",
        "mode.performance": "Desempenho",
        "fan.auto": "Auto",
        "fan.max": "Máx",
        "fan.custom": "Personalizado",
        "fan.cpu": "Ventoinha CPU",
        "fan.gpu": "Ventoinha GPU",
        "scen.intro": "Silencioso, Padrão e Desempenho, mais Auto / Máx / Personalizado nas ventoinhas — os mesmos controlos do NitroSense no Windows. Associe um perfil e um modo de ventoinha a uma app em execução; aplicam-se enquanto o processo estiver aberto.",
        "scen.now": "Agora  {mode}  ·  ventoinhas {fan}{extra}",
        "scen.rule_extra": "  ·  regra {name}",
        "scen.rules": "REGRAS DE APLICATIVOS",
        "scen.apply": "Aplicar automaticamente",
        "scen.add": "Adicionar",
        "scen.hint": "Vale o primeiro processo em execução que coincidir. Um clique manual de modo ou ventoinha no INÍCIO ou aqui pausa a aplicação automática por 45 segundos.",
        "scen.empty": "Ainda não há regras. Escolha um app em execução e Adicionar.",
        "scen.remove": "Remover",
        "scen.running": "em execução",
        "scen.rule": "{mode}  ·  {fans}",
        "scen.rule_custom": "{mode}  ·  {fans} {cpu}/{gpu}",
        "mon.hint": "Últimos ~30 minutos (1 Hz). CPU, GPU, RAM, SWAP, rede e disco.",
        "res.processor": "PROCESSADOR",
        "res.options": "OPÇÕES",
        "res.usage": "USO",
        "res.memory": "MEMÓRIA",
        "res.graphics": "GRÁFICOS",
        "res.network": "REDE",
        "res.storage": "ARMAZENAMENTO",
        "res.battery": "BATERIA",
        "res.processes": "PROCESSOS",
        "res.logical": "Mostrar uso por CPU lógica",
        "proc.filter": "Filtrar processos",
        "proc.name": "NOME",
        "proc.pid": "PID",
        "proc.cpu": "CPU",
        "proc.memory": "MEMÓRIA",
        "proc.end": "Encerrar",
        "light.page": "ILUMINAÇÃO",
        "light.keyboard": "TECLADO",
        "light.display": "TELA",
        "light.night_section": "LUZ NOTURNA",
        "light.timeout": "Desligar teclado após 30 s sem uso",
        "light.timeout_hint": "Clique no teclado ou no interruptor. O ANV15-51 é de uma cor — Fn cicla Desligado / médio / máximo.",
        "light.brightness": "Brilho",
        "light.brightness_pct": "Brilho  ·  {pct}%",
        "light.lcd": "Substituição do LCD",
        "light.night": "Luz noturna",
        "light.night_hint": "Tela mais quente (GNOME). Temperatura em Kelvin.",
        "light.rgb": "RGB de quatro zonas",
        "light.caps": "CAPS",
        "light.num": "NUM",
        "light.scroll": "SCROLL",
        "set.driver": "DRIVER",
        "set.battery": "BATERIA",
        "set.startup": "INÍCIO",
        "set.install": "Instalar driver Linuwu",
        "set.limit": "Limite de carga 80%",
        "set.limit_hint": "Para de carregar aos 80% para poupar a bateria.",
        "set.usb": "USB a carregar com o notebook desligado",
        "set.usb_hint": "Carregar um celular nesta porta USB com o notebook desligado.",
        "set.calibrate": "Calibração",
        "set.calibrate_btn": "Iniciar calibração da bateria",
        "set.calibrate_hint": "Ciclo completo 100→0→100. Mantenha o carregador ligado.",
        "set.calibrate_title": "Calibrar a bateria?",
        "set.calibrate_body": "Ciclo completo 100→0→100. Mantenha o carregador ligado.",
        "set.boot": "Animação / som de arranque",
        "set.boot_hint": "Este chassis não expõe o nó de animação de arranque.",
        "set.autostart": "Abrir o NitroSense no login",
        "set.autostart_hint": "Abre a janela quando você entra na sessão.",
        "set.hotkey": "Tecla N dedicada",
        "set.hotkey_hint": "A tecla Nitro da Acer (PROG1) abre ou foca esta janela.",
        "set.language": "Idioma",
        "set.language_hint": "Inglês ou português do Brasil. Aplica na hora.",
        "set.tgp": "POTÊNCIA DA GPU",
        "set.tgp_hint": "TGP do RTX via nvidia-smi (não é Linuwu). Padrão e Boost. A última escolha volta no login, sem pedir senha.",
        "set.tgp_now": "Agora {watts} W",
        "set.tgp_default": "Padrão  ·  {watts} W",
        "set.tgp_boost": "Boost  ·  {watts} W",
        "set.tgp_missing": "Nenhuma GPU NVIDIA com limite de potência legível (nvidia-smi).",
        "set.install_title": "Instalar driver",
        "set.install_body": "No terminal:\n\n{setup}\n\nPrecisa de sudo.",
        "fact.driver": "Driver",
        "fact.firmware": "Firmware",
        "fact.profile": "Perfil",
        "fact.choices": "Opções",
        "fact.model": "Modelo",
        "fact.threads": "Threads",
        "fact.frequency": "Frequência",
        "fact.temperature": "Temperatura",
        "fact.used": "Em uso",
        "fact.available": "Disponível",
        "fact.cached": "Cache",
        "fact.swap": "Swap",
        "fact.interface": "Interface",
        "fact.type": "Tipo",
        "fact.ipv4": "IPv4",
        "fact.link": "Ligação",
        "fact.status": "Estado",
        "fact.power": "Potência",
        "fact.energy": "Energia",
        "fact.cycles": "Ciclos",
        "tile.ram": "RAM",
        "tile.swap": "SWAP",
        "tile.net": "REDE",
        "tile.disk": "DISCO",
        "tile.memory": "Memória",
        "tile.download": "Download",
        "tile.upload": "Upload",
        "tile.charge": "Carga",
        "tile.power": "Potência",
        "tile.total": "Total",
        "chart.cpu_temp": "Temperatura da CPU",
        "chart.gpu_temp": "Temperatura da GPU",
        "chart.cpu_load": "Carga da CPU",
        "chart.gpu_load": "Carga da GPU",
        "chart.ram_load": "Carga da RAM",
        "chart.ram_used": "RAM em uso",
        "chart.swap_load": "Carga do SWAP",
        "chart.swap_used": "SWAP em uso",
        "chart.net_down": "Rede · download",
        "chart.net_up": "Rede · upload",
        "chart.disk_read": "Leitura do disco",
        "chart.disk_write": "Escrita do disco",
        "usb.off": "Desligado",
        "usb.until": "Até {pct}%",
        "ok": "OK",
        "cancel": "Cancelar",
        "start": "Iniciar",
        "swap.off": "SWAP  ·  desligado",
        "off": "off",
    },
}

_lang = "en"


def detect_lang() -> str:
    env = os.environ.get("NITROSENSE_LANG") or ""
    if env in _STRINGS:
        return env
    try:
        data = load_ui()
        lang = str(data.get("lang") or "")
        if lang in _STRINGS:
            return lang
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    loc = (os.environ.get("LANG") or os.environ.get("LC_ALL") or "").replace("-", "_")
    if loc.lower().startswith("pt"):
        return "pt_BR"
    return "en"


def load_ui() -> dict:
    try:
        data = json.loads(UI_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_ui(**fields) -> None:
    UI_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = load_ui()
    payload.update(fields)
    UI_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def save_lang(lang: str) -> None:
    if lang not in _STRINGS:
        lang = "en"
    save_ui(lang=lang)


def set_lang(lang: str) -> str:
    global _lang
    _lang = lang if lang in _STRINGS else "en"
    return _lang


def lang() -> str:
    return _lang


def t(key: str, **kwargs) -> str:
    table = _STRINGS.get(_lang) or _STRINGS["en"]
    text = table.get(key) or _STRINGS["en"].get(key) or key
    if kwargs:
        return text.format(**kwargs)
    return text


set_lang(detect_lang())
