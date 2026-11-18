# DeckyScaler

DeckyScaler is a [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for the Steam Deck and other Linux handhelds. It puts [OptiScaler](https://github.com/optiscaler/OptiScaler) into a game straight from Game Mode, so you can try FSR 4, XeSS or frame generation without going to Desktop Mode, and Unpatch leaves the game as it was. It also brings what OptiScaler can use: any of its versions, libraries such as ANR, and newer Proton builds.

> DeckyScaler (formerly Decky Framegen) is a continuation of [xXJSONDeruloXx/Decky-Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen). Its builds don't include OptiScaler: games are patched from versions in the plugin's OptiScaler library (`~/deckyscaler/library`), downloaded straight from OptiScaler's releases. Download a version under **OptiScaler versions** → *Download versions…* before patching a game. Report problems in [this repository's issues](https://github.com/arttttt/DeckyScaler/issues).

## What This Plugin Does

OptiScaler takes the upscaling a game already has (DLSS, FSR 2 and newer, or XeSS) and runs the one you pick in its place: FSR 3.1 or FSR 4, XeSS, or DLSS on NVIDIA. It can add frame generation too.

DeckyScaler downloads OptiScaler from its own releases, stable or nightly, and each game runs the version you pick for it. The settings come from that version's `OptiScaler.ini`, so a new OptiScaler brings its new settings without waiting for a plugin update. With OptiScaler 10 a game can also get libraries OptiScaler doesn't ship: ANR's frame generation, or FSR and XeSS files you bring. GE-Proton and Proton-CachyOS install from the plugin as well, and they fetch the driver file FSR 4 needs on Linux.

Every patch is recorded, so Unpatch undoes exactly what it did, launch options included. A game the original Decky Framegen patched can be reset to its own files.

DeckyScaler itself runs nothing inside a game: a game loads OptiScaler and the libraries picked for it. The plugin's settings reach a game when it is patched, on each change, and when the game closes; to change something while the game runs, use OptiScaler's in-game menu.

## Features

- **Quick Access panel**: pick a Steam game, see its patch, FSR 4 and libraries at a glance, and patch or unpatch it; **Open DeckyScaler** opens the plugin's page.
- **OptiScaler**: **DeckyScaler → OptiScaler** downloads and removes OptiScaler versions (see [Where OptiScaler comes from](#where-optiscaler-comes-from)), sets the libraries every game gets (see [Libraries](#libraries)) and holds the **Global settings** (see [OptiScaler settings](#optiscaler-settings)).
- **Games**: **DeckyScaler → Games** lists every game the plugin patched, with its OptiScaler version, proxy DLL and anything wrong with the patch; a Steam game opens its page, a directory patched by path is unpatched right there.
- **Game pages**: a **DeckyScaler** button on a game's page in Steam opens the game's page in the plugin: its OptiScaler version, proxy DLL, libraries and **OptiScaler settings**, and Patch / Unpatch.
- **Proton builds**: **DeckyScaler → Proton** installs GE-Proton and Proton-CachyOS into Steam and removes them (see [Proton builds](#proton-builds)).
- **Advanced**: **DeckyScaler → Advanced** patches any directory, such as a game outside Steam, and copies launch options or the launch wrapper's commands (see [Games outside Steam](#games-outside-steam) and [The launch wrapper](#the-launch-wrapper)).
- **Updates**: **DeckyScaler → Updates** checks this repository's releases (on opening, and by a button) and installs a newer one through Decky; the Quick Access panel says when one is out. **Developer mode** there adds development builds, at your own risk.
- **OptiScaler Wiki**: a button on the Advanced page opens OptiScaler's documentation.
- **Steam installs**: native and Flatpak Steam both work, with nothing to set.

## How to Use

1. **Install the plugin**: download `DeckyScaler.zip` from this repository's [Releases](https://github.com/arttttt/DeckyScaler/releases). In Decky, turn on **Developer mode** in its General settings, then in its Developer settings press *Browse* next to **Install Plugin from ZIP File** and pick the zip; Decky first warns that it hasn't reviewed the plugin. Later releases install from **DeckyScaler → Updates**.
2. **Get OptiScaler**: **DeckyScaler → OptiScaler → OptiScaler versions** → *Download versions…*, pick stable releases or nightly builds, and download a version.
3. **Patch a game**: in the Quick Access panel pick the game under **Steam game** and press **Patch with dxgi.dll** (or the proxy DLL picked for it). The plugin places OptiScaler in the game's directory and sets the game's launch options. To choose the game's OptiScaler version, proxy DLL or libraries first, open its page: **Open game page**, or the **DeckyScaler** button on its page in Steam.
4. **In the game**: turn on its DLSS, FSR or XeSS upscaling: that is what OptiScaler replaces. OptiScaler's menu (the Insert key by default; map it to a button with Steam Input) picks the upscaler and frame generation.
5. **Unpatch**: **Unpatch this game** removes what the patch placed, puts back the game files it replaced, and gives the game its launch options from before.

### Games outside Steam
**DeckyScaler → Advanced** patches a directory: pick the OptiScaler version and proxy DLL, then **Select directory** (where the game's EXE is) → **Patch directory**. **Copy launch options** copies the launch options the game then needs, for a non-Steam shortcut in Steam; another launcher needs the same `WINEDLLOVERRIDES` set its own way. **Unpatch directory**, or the directory's row in **DeckyScaler → Games**, undoes the patch.

### The launch wrapper
The wrapper patches a game each time it starts instead of once from the plugin. **Copy Patch Command** (on the Advanced page) copies `~/deckyscaler/patch %command%` for a game's launch options. While it is there, every launch checks the patch and patches again when a placed file went missing or another version or proxy DLL is asked for, even after DeckyScaler is uninstalled.

- It works as Steam launch options, for Lutris games (it finds the game's directory from Lutris), and as a wrapper in launchers that run one before the game, such as Heroic.
- Variables set before it: `DECKYSCALER_VERSION=<version>` (for example `nightly-20261116`; unset keeps the version the game is patched with, else the newest), `DLL=<proxy DLL>` (default `dxgi.dll`), `PRESERVE_INI=false` (starts the game's `OptiScaler.ini` over), and OptiScaler settings (see [below](#optiscaler-settings-as-environment-variables)).
- The wrapper doesn't know the game's Proton prefix, so it can't link FSR 4's driver DLL (see [FSR 4](#fsr-4)): a game keeps the link a patch from the plugin made, but if the wrapper has to patch it again, the link is gone until the next patch from the plugin.
- To take it out, put the command **Copy Unpatch Command** copies (`~/deckyscaler/unpatch %command%`) there instead and start the game once; then the launch option can go.

### Games patched by Decky Framegen
A game the original Decky Framegen patched says so in its status ("Patched by Decky Framegen"), and DeckyScaler won't patch over it. **Unpatch** first shows what it will do: the game files it restores from Decky Framegen's backups, the files it removes, and any it can't restore (Steam's *Verify integrity of game files* brings those back). Confirming resets the game to its own files and takes the plugin's launch options out (the confirmation shows what they become).

### OptiScaler settings
**DeckyScaler → OptiScaler → Global settings** sets what every game gets; a game's page (**OptiScaler settings** there) sets the game's own, which stay over the global ones. A global change never touches a value a game sets itself. Every setting, its values and its help come from the `OptiScaler.ini` of the version in use, so a new OptiScaler version brings its new settings with no plugin update, and settings it doesn't take are kept for the versions that do. Settings are written into a game's `OptiScaler.ini` when it is patched, on each change, and when the game closes; a running game is left alone until then, so OptiScaler doesn't save over them.

- A setting left on auto keeps OptiScaler's default.
- A setting set here replaces a change to it in OptiScaler's in-game menu once the game closes; settings left on auto stay as the menu saved them.

### OptiScaler settings as environment variables
Games started through the [launch wrapper](#the-launch-wrapper) also take OptiScaler settings from environment variables set before it; a game patched from the plugin's panel doesn't read them. This is useful for giving several games the same settings by the time they start.

For example, considering the following sample from an OptiScaler 10 `OptiScaler.ini`:
```
[Upscalers]
Dx11Upscaler=auto
Dx12Upscaler=auto
VulkanUpscaler=auto

[FrameGen]
Enabled=auto
FGInput=auto
FGOutput=auto
DebugView=auto
DrawUIOverFG=auto
```
`Dx12Upscaler=ffx` sets DX12 games to AMD's FidelityFX upscaler (FSR 3.1, or FSR 4 where it runs; OptiScaler 0.9.x calls it `fsr31`). This works because the option name `Dx12Upscaler` is unique throughout the file, but for options that appear multiple times like `Enabled`, you prefix the option name with the section name like `FrameGen_Enabled=true`.
You can provide section names for all options if you want to be explicit. You can also prefix `Section_Option` with `OptiScaler` to ensure no conflict with other variables.

Here's the breakdown of supported formats:
- `OptiScaler_Section_Option=value` - Full format (foolproof)
- `Section_Option=value` - Short format (recommended)
- `Option=value` - Minimal format (only works if the option name appears once in OptiScaler.ini)

**Example:**
```bash
# Enable frame generation with XeFG output
FrameGen_Enabled=true FGInput=fsrfg FGOutput=xefg ~/deckyscaler/patch %command%

# Set the DX12 upscaler to FidelityFX (FSR 3.1 / FSR 4) on OptiScaler 10
Dx12Upscaler=ffx ~/deckyscaler/patch %command%
```

**Notes:**
- Only options the game's `OptiScaler.ini` already has are set; the names and values are those of its OptiScaler version.
- Variables are applied on every launch, after the plugin's own settings, so they win over them and over what OptiScaler's menu saved.
- A value set only by a variable stays in the game's `OptiScaler.ini` after the game closes; a setting the plugin also sets is written back to the plugin's value when the game closes, and the variable sets it again on the next launch.
- Hyphenated section names like `[V-Sync]` can be accessed like `VSync_Option=value`
- If an option name appears in multiple sections of the OptiScaler.ini file, use the `Section_Option` or `OptiScaler_Section_Option` format

### FSR 4

The plugin does not pick an FSR 4 model: OptiScaler does. OptiScaler 10 uses the best model the GPU supports (`Fsr4Model` on auto); `FSR_Fsr4GpuSupport` overrides the support it detects (INT8 Lite is the smaller model meant for APUs). OptiScaler 0.9.x supports RDNA4 and RDNA3 desktop GPUs officially; `FSR_Fsr4ForceEnableInt8=true` forces INT8 elsewhere, but does not make older non-INT8 hardware compatible. `FSR_Fsr4EnableWatermark=true` shows which FSR runs.

On Linux FSR 4 also needs AMD's driver DLL (`amdxcffx64.dll`), which neither OptiScaler nor Valve's Proton ship. GE-Proton and Proton-CachyOS (both installable from [**DeckyScaler → Proton**](#proton-builds)) download it into the game's prefix when the game is launched with `PROTON_FSR4_UPGRADE=1`. On an AMD GPU the plugin adds that variable to the launch options it writes when the game's Proton reads it, and links the DLL next to OptiScaler, the only place OptiScaler loads it from. The game's status says whether FSR 4 is already in the prefix, will be downloaded on the next launch, or needs another Proton. Without the DLL, OptiScaler's upscaler list ends at FSR 3.1.5.

### Proton builds
**DeckyScaler → Proton** installs custom Proton builds into Steam. *Download builds…* lists the ten newest releases of GE-Proton, Proton-CachyOS and Proton-CachyOS's x86_64_v3 variant (built for newer CPUs; for experimenting), checks each download against the checksum GitHub publishes, and unpacks it into the `compatibilitytools.d` of the Steam install that is running (or the only one that has run). *Manage installed…* lists every build Steam would find, including ones other tools installed, with the games set to use it, and removes one after a warning naming those games; builds installed for every user of the device are only listed.

- Steam lists builds when it starts: the page has a *Restart Steam* button (and says when a restart is due), and the download dialog offers it right after an install. It asks first: a running game closes with Steam.
- A game's Proton is chosen in Steam: the game's Properties → Compatibility.
- To update a build, download the newer release: it is installed next to the old one, which stays for going back until you remove it. Once Steam has restarted, the page offers to move the games set to use an older build of the same kind to the new one in one tap (or to keep them where they are).

### Libraries
OptiScaler 10 takes libraries beside its own: providers, folders it selects by name (ANR's frame generation is one), and newer copies of the DLLs it loads itself (`libxess.dll`, `amd_fidelityfx_upscaler_dx12.dll`, `libxess_fg.dll`, `nvngx_dlss.dll`…). **DeckyScaler → OptiScaler → Libraries** puts them into games:

- *Download libraries…* lists what can be downloaded under its button (now ANR's frame generation): pick the library, then one of its versions. It comes from the project's releases on GitHub, checked against the checksum GitHub publishes; the plugin never ships it.
- *Add from file…* adds what you brought onto the device (in Desktop Mode it is in Downloads; a USB drive is under `/run/media`): a provider's zip or folder, a DLL, or a zip of several DLLs such as Intel's XeSS SDK.
- Every provider on the device goes into every game patched with OptiScaler 10, picked or not, so OptiScaler's own overlay offers it. OptiScaler lists a frame generation provider such as ANR only while *FG Input* is *DLSSG via Nvngx*: set it, then pick *Apex Neural Rendering FG* in the *FG Nvngx* list that takes *FG Output*'s place, save, and restart the game. Two versions of one provider share its folder name: a game gets the picked one, else the one added last. A DLL goes in only when picked: OptiScaler finds it through the ini key the pick sets, and its overlay has no such choice.
- Pick a library for every game per slot, **Upscaler** and **Frame generation**, and a game's own on its page (or *None*). Picking it is what turns it on: the patch copies it into the game (a provider into OptiScaler's `custom/`, a DLL into `OptiScaler/user-libraries/`, never over OptiScaler's own copy) and sets the ini keys that select and find it, ANR's own settings included. Those keys show as *Set by …* in the settings and change with the library. A frame generation DLL is only pointed at: turn frame generation on in OptiScaler's settings (`FGInput`, `FGOutput`). ANR needs a game with DLSS frame generation turned on.
- A pick reaches a patched game only when it is patched again, so picking one asks to patch the games it reaches right away (*Patch again now*; running games are skipped). *Later* leaves a note under the picks with *Apply to it* (or *Apply to them*); the launch wrapper keeps a game's picks until then. A library downloaded, added or removed reaches Steam games at their next launch (the launch wrapper patches them again) and other patched games once patched again. Unpatching removes what a library put into the game, its logs included.
- OptiScaler 0.9.x takes no libraries. In a game, OptiScaler's overlay names the upscaler and frame generation running (XeSS with its version); its log lists where each DLL was loaded from.

## Technical Details

### Where OptiScaler comes from
Builds of this plugin don't include OptiScaler. **OptiScaler versions** → *Download versions…* fetches versions straight from OptiScaler's own releases ([stable](https://github.com/optiscaler/OptiScaler/releases), [nightly](https://github.com/optiscaler/OptiScaler-nightly/releases)), checks each download against its published checksum, and keeps it in `~/deckyscaler/library`; *Manage downloaded…* downloads one again or removes one. A patch places the version picked for it (the newest, unless you pick another) in the game's directory as symlinks into the library, so games hold no copies of OptiScaler; only `OptiScaler.ini` is copied, since OptiScaler saves each game's settings there. It backs up any game file it replaces and records what it did, so Unpatch undoes exactly that. A version games are linked to can't be removed until they are unpatched.

### Logs
- Decky's log of the plugin: `~/homebrew/logs/DeckyScaler/`
- The launch wrappers: `/tmp/deckyscaler-patch.log` and `/tmp/deckyscaler-unpatch.log`
- OptiScaler's own log, when it writes one: `OptiScaler.log` in the game's directory

## Development

How to build, test, and try a work-in-progress build on a device: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

### Core Technologies
- **[Kurt Himebauch (xXJSONDeruloXx)](https://github.com/xXJSONDeruloXx/Decky-Framegen)** - Decky Framegen, the plugin DeckyScaler continues
- **[Cdozdil/OptiScaler Team](https://github.com/optiscaler/OptiScaler)** - OptiScaler, which everything this plugin puts into a game is for
- **[Nukem9](https://github.com/Nukem9/dlssg-to-fsr3)** - dlssg-to-fsr3, the frame generation provider OptiScaler ships and uses by default
- **[FakeMichau](https://github.com/FakeMichau/fakenvapi)** - fakenvapi, shipped with OptiScaler 0.9.x for AMD and Intel GPUs
- **[Apex Compute](https://github.com/apex-compute/ANR)** - ANR, the frame generation the Libraries page downloads
- **[GloriousEggroll](https://github.com/GloriousEggroll/proton-ge-custom)** and **[CachyOS](https://github.com/CachyOS/proton-cachyos)** - GE-Proton and Proton-CachyOS, which the Proton page installs
- **[Artur Graniszewski](https://github.com/artur-graniszewski/DLSS-Enabler)** - DLSS Enabler, a frame generation provider OptiScaler can use with the DLL you bring
- **[7-Zip](https://www.7-zip.org/)** by Igor Pavlov - the plugin ships its static Linux build (`tools/7zzs`, GNU LGPL; license in `tools/7zzs-License.txt`) to unpack OptiScaler archives
- **[SteamDeckHomebrew](https://github.com/SteamDeckHomebrew)** - Decky Loader, its plugin API and the plugin template this project started from

### Community & Documentation
- **[Deck Wizard](https://www.youtube.com/watch?v=o_TkF-Eiq3M)** - Extensive community support including comprehensive guides, promotional content, thorough testing and feedback, custom artworks, and tutorial videos. Deck Wizard's passionate advocacy and continuous support have been instrumental in the original Decky Framegen's success.

- **The DLSS2FSR Community** - Ongoing support and guidance for understanding the various mods and tools
