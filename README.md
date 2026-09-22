# NitroSense Linux

Clone **não oficial** do NitroSense para Acer Nitro no Linux. Testado no **ANV15-51**.
Não é da Acer. A GUI é GTK4; o firmware é o mesmo. Fans, modos e bateria passam pelo driver [Linuwu Sense](https://github.com/PXDiv/Div-Linuwu-Sense) (o mesmo motor que o DAMX já cobriu neste modelo).

## Instalar (.deb)

Cada merge em `main` gera uma [Release](https://github.com/rodriguesfas/nitrosense/releases) com tag `vX.Y.Z` e o pacote `nitrosense_X.Y.Z_all.deb`.

```bash
sudo apt install ./nitrosense_*_all.deb
nitrosense                 # GUI
nitrosense-setup           # driver Linuwu (fans, perfil, bateria) — pede sudo
```

O `.deb` traz a app. O módulo de kernel **não** vai no pacote (depende do teu kernel). Depois do driver, faz logout/login (grupo `linuwu_sense`).

## Correr a partir da fonte

```bash
git clone https://github.com/rodriguesfas/nitrosense.git
cd nitrosense
./bin/nitrosense
./install-hotkey.sh        # tecla N (KEY_PROG1 → XF86Launch1)
./setup.sh                 # driver Linuwu
```

Dependências da GUI: `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`.

## O que replica do Windows

| NitroSense | Aqui |
|---|---|
| Temps CPU / GPU | Painel (coretemp + nvidia-smi) |
| RAM usada / total | HOME (rodapé) + MONITORING |
| RPM das ventoinhas | Painel, depois do driver |
| Silencioso / Padrão / Desempenho | Perfis ACPI. Turbo **não existe** neste chassis (o firmware recusa) |
| Auto / Max / Custom | HOME — Custom escreve `cpu%,gpu%` no sysfs Linuwu |
| Limite de carga 80% | Aba Bateria |
| Calibração de bateria | Aba Bateria |
| USB charging com o PC desligado | Aba Bateria |
| Timeout do backlight | Aba Teclado |
| RGB 4 zonas | Só se o sysfs `four_zoned_kb` aparecer. O ANV15-51 é backlight de **uma cor** |
| Tecla N | `KEY_PROG1` (Acer WMI) → XF86Launch1 + listener sem grab |

TGP da GPU (60 W vs 75 W) é outro problema (nvidia-powerd / Dynamic Boost), não desta app.

## Branches

| Branch | Uso |
|---|---|
| `dev` | Trabalho do dia a dia |
| `main` | Estável. Push/merge aqui gera a tag `v$(cat VERSION)` e o `.deb` |

Antes de mergear `dev` → `main`, sobe o ficheiro `VERSION` (sem isso o workflow recusa, porque a tag já existe).

## Árvore

```
nitrosense/     GUI + hardware + sensores
bin/            launcher, hotkey, helper pkexec, fixperms
packaging/      build-deb.sh
.github/        release do .deb em main
setup.sh        driver Linuwu
```

Auditoria vs Windows: [AUDIT.md](AUDIT.md).
