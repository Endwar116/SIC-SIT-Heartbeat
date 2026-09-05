# Install

Three environments, one state directory (`$HEARTBEAT_HOME`, default `~/.sic-sit-heartbeat`).
Python 3.9+ standard library only. No pip.

## 1. Claude Code — CLI, VS Code extension, desktop app

All three share `~/.claude/settings.json`, so one install covers them:

```bash
git clone https://github.com/Endwar116/SIC-SIT-Heartbeat && cd SIC-SIT-Heartbeat
./install/install.sh            # backs up settings.json, adds three PreToolUse hooks
python3 ledger/ledger.py verify # ✅ chain intact — 0 rounds
./heartbeat/tick.sh             # one governed tick; prints an anchor line
```

Gates now fire before `Bash`, `Monitor`, and `Workflow` calls. Try it:

```
> rm -rf ./scratch
⛔ file-governance: hard delete detected (rm). Rule: delete = move into ~/.sic-sit-heartbeat/trash + write TOMBSTONE.md ...
```

**Heartbeat inside a Claude Code session** — use the built-in `Monitor` tool with
`./heartbeat/run_loop.sh 3600`; each line it prints becomes one event in the conversation.
Because `monitor_dedup.py` is now a gate, mounting a second identical loop is blocked until the
first is verified dead or stopped.

**Print the anchor.** After each round the ledger prints `⚓ R<round> · seq<n> · <hash16>`.
Ending a reply with that line lets a transcript be joined to the ledger later. Keep the format
exact (half-width digits, lowercase hex); `ledger/anchor.py check` finds drift.

## 2. VS Code without Claude Code

The gates are `PreToolUse` hooks — they need a harness that exposes a pre-tool hook.
For other assistants, run the **ledger + heartbeat** half (below) and adapt `gates/_hook.py`
to your assistant's hook shape (stdin JSON in, exit code out). The gates themselves are
harness-agnostic Python.

## 3. Terminal only (cron / launchd / systemd)

```bash
# cron — hourly tick, log on the INTERNAL disk
0 * * * * HEARTBEAT_HOME=$HOME/.sic-sit-heartbeat /path/SIC-SIT-Heartbeat/heartbeat/tick.sh >> $HOME/.sic-sit-heartbeat/logs/tick.log 2>&1
```

macOS launchd: copy `install/launchd/com.example.heartbeat.plist` to `~/Library/LaunchAgents/`,
edit the paths, then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.heartbeat.plist`.

> **Keep `StandardOutPath` / `StandardErrorPath` on the internal disk.** If launchd cannot open
> the log file (external or not-yet-mounted volume) it returns exit 78 *before running anything*
> and writes nothing — the job looks idle, forever. `heartbeat/health.py` flags this configuration.

## Environment

| var | default | meaning |
|---|---|---|
| `HEARTBEAT_HOME` | `~/.sic-sit-heartbeat` | all state |
| `HEARTBEAT_AGENT` | `agent` | `entity.name` written into rounds |
| `HEARTBEAT_MODEL` | `unknown` | `entity.model` — set it from your harness; a model cannot attest itself |
| `HEARTBEAT_INBOX` | `$HEARTBEAT_HOME/inbox` | directory the tick counts |
| `HEARTBEAT_STALE_HOURS` | `24` | when a periodic job's log counts as stale |
| `HEARTBEAT_EXTERNAL_PREFIXES` | `/Volumes/,/mnt/,/media/` | log paths considered external |

## Moving the repo

Hooks embed the absolute clone path. A missing hook target exits 127, which the harness treats as
*non-blocking* — the gate is silently off. After moving: `./install/install.sh` again, or check with
`./install/install.sh --check` (also run by `heartbeat/health.py`).

## Uninstall

`./install/install.sh --uninstall` removes only the hook entries that point into this repo (a `.bak_*`
copy of settings.json is kept). Your ledger and trash are yours.

## The `Stop` hook and the event-gated loop

`install.sh` now also adds one `Stop` hook — `gates/turn_exit.py` — which runs when the agent ends a turn: an
unrecorded promise or an untouched locked item blocks the exit once (the reason is shown to the agent), a completion
claim without a receipt is recorded as a claim. `install.sh --check` covers it; `--uninstall` removes it.

For a scheduler, prefer `heartbeat/run_loop.sh --event` (ticks on inbox / pending-ledger / `touch $HEARTBEAT_HOME/wake`
events, plus a liveness tick every `HEARTBEAT_FALLBACK` seconds) over a fixed timer: the timer is what manufactures
idle spin. Markers for the turn-exit gate live in `$HEARTBEAT_HOME/config/turn_exit.json` (optional).
