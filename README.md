# histpick

```
histpick: powershell history  12/12  6 chosen
filter:  (type to filter, words in any order)
 [ ]   ping github.com
 [x]   winget install --id Git.Git -e
 [ ]   cls
 [x]   cd spacetrail
 [x]   git clone https://github.com/A2M33/spacetrail
 [ ]   Get-ChildItem -Recurse -Filter *.log |  (+1 line)
 [x]   winget install --id Python.Python.3.12 -e
 [ ]   code .
 [ ]   Copy-Item .env.example .env
 [ ]   git log --oneline -5
 [x]   .venv\Scripts\pip install -r requirements.txt
 [x]   python -m venv .venv

↑↓ move  tab choose  ctrl+a all  ctrl+o chosen only  ctrl+u clear  enter review  esc clear/cancel
```

*One frame of the picker over a made-up PowerShell history, printed by [tools/demo/make_picker.py](tools/demo/make_picker.py) with the picker's own drawing code. In the terminal the chosen rows are cyan and the cursor row is highlighted.*

histpick lists your recent shell commands. You tick the ones you want to keep and it writes them to a script you can run again later, for example the setup steps you got working today and will need on another machine next month.

It reads PowerShell, bash, zsh and fish history. PowerShell history becomes a `.ps1` file, and the other shells get a script with the right shebang.

## Install

**Windows, no Python needed.** Download `histpick.exe` from the [latest release](https://github.com/A2M33/histpick/releases/latest). Windows SmartScreen may warn you the first time because the file isn't code-signed. Click "More info", then "Run anyway". GitHub Actions builds the file from this repository for each release.

**With Python 3.10 or newer** (Windows, Linux, macOS). histpick needs nothing outside the standard library.

```bash
pip install git+https://github.com/A2M33/histpick
```

## Use

```bash
histpick              # pick commands, save as histpick-<date>.ps1 (or .sh)
histpick -o setup     # save as setup.ps1 / setup.sh
```

After saving, histpick prints the full path and the command that runs the script. On Windows that command is `powershell -ExecutionPolicy Bypass -File "<path>"`, because Windows refuses to run unsigned `.ps1` files by default.

| Key | Action |
| --- | --- |
| `↑` `↓`, `PgUp` `PgDn` | Move |
| `Tab` | Choose or unchoose a command |
| Typing | Filter the list. `git push` shows commands that contain both words, in any order |
| `←` `→`, `Backspace`, `Delete` | Edit the filter |
| `Ctrl+U` | Clear the filter |
| `Ctrl+A` | Choose everything that matches the filter |
| `Ctrl+O` | Show only the chosen commands; press again to show all |
| `Enter` | Review the chosen commands (with nothing chosen, it takes the highlighted one) |
| `Esc` | Clear the filter; press it again to cancel |

The list shows the newest command first and each command once. The top line counts the matches, like `12/300`. If you highlight a multi-line command, a pane under the list shows all of its lines.

A command you ran twice goes where you ran it last. The review screen shows the chosen commands in the order the script will run them, and you can change that order before you save:

| Key | Action |
| --- | --- |
| `↑` `↓` | Select a command |
| `Ctrl+↑` `Ctrl+↓`, or `U` `D` | Move it up or down in the script |
| `X`, `Backspace` or `Delete` | Remove it |
| `Enter` | Save |
| `Esc` | Go back to the list |

### Without the picker

```bash
histpick --list                 # numbered list, 1 = newest
histpick --pick "7-5 2" -o fix  # save commands 7, 6, 5 and 2, in that order
histpick --last 4 --print       # print the last 4 commands as a script
histpick --grep docker          # only offer commands containing "docker"
```

`--pick` writes the commands in the order you list the numbers. `--last` keeps the order you ran them in.

Other options: `--shell bash` reads another shell's history, `--limit 500` offers more commands (default 300) and `--force` overwrites an existing file.

## The saved script

```powershell
# Saved with histpick from PowerShell history on 2026-10-29 13:10
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$global:LASTEXITCODE = 0

winget install --id Git.Git -e
if ($LASTEXITCODE) { exit $LASTEXITCODE }

git clone https://github.com/A2M33/spacetrail
if ($LASTEXITCODE) { exit $LASTEXITCODE }
```

The script stops at the first error, as you would if you were typing the commands. `$ErrorActionPreference` stops it when a PowerShell cmdlet fails. Windows PowerShell 5.1 ignores the exit code of programs like `git` and `winget`, so histpick adds a `$LASTEXITCODE` check after each command. bash and zsh scripts get `set -euo pipefail`. fish has no such switch, so histpick puts `or exit $status` after each command in a fish script.

Read the script before you run it. Your history may hold one-off commands, passwords typed in clear text or paths that exist only on your machine. histpick puts a `!` next to commands that mention a password, token, secret or API key, or that contain an AWS or GitHub key. You see the mark in the picker and in `--list`, and histpick warns you before it saves such a command. The check matches words and key formats, so it can miss a secret, and it flags harmless commands like `npm token list` too.

## Where history comes from

| Shell | File | Note |
| --- | --- | --- |
| PowerShell | `%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt`, or `~/.local/share/powershell/PSReadLine/ConsoleHost_history.txt` on Linux and macOS | Saved after every command |
| bash | `~/.bash_history` (or `$HISTFILE`) | bash writes it when the shell exits; run `history -a` first to include the current session |
| zsh | `~/.zsh_history` | Plain and extended formats |
| fish | `~/.local/share/fish/fish_history` | |

Without `--shell`, histpick uses the shell it was started from, or else the history file that changed last. It keeps multi-line commands whole and leaves its own calls out of the list.

## Development

```bash
git clone https://github.com/A2M33/histpick
cd histpick
pip install -e ".[dev]"
pytest
```

The picker logic lives in `PickerState` (`src/histpick/picker.py`) with no terminal code, so the tests drive it directly. GitHub Actions runs them on Windows, Linux and macOS.

To print the picker frame at the top of this page again, run `python tools/demo/make_picker.py`.

## License

MIT
