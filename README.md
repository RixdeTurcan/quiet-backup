# quiet-backup

quiet-backup is a small Debian-friendly backup daemon designed to make periodic backups with low impact on CPU, disk and I/O activity.

Instead of trying to copy everything as fast as possible, quiet-backup scans configured paths, detects changed files, and spreads backup operations over time. The goal is to keep backups running regularly without noticeably disturbing the machine.

## What it does

quiet-backup runs as a systemd service and performs repeated backup cycles.

For each configured group, it:

- scans one or more base directories with glob patterns
- tracks file metadata in a JSON state file
- detects new or modified files
- waits a configurable delay before backing up a changed file
- copies files to one or more destinations
- optionally compresses backups with gzip
- limits backup rate to avoid saturating the system
- keeps only a configurable number of versions per file

## Design goals

This project is built around a few simple ideas:

- **Low impact**: backups should not monopolize CPU, disk or I/O
- **Simple configuration**: one JSON file, readable and easy to modify
- **Continuous service**: the daemon runs permanently under systemd
- **Periodic scanning**: no kernel watcher is required
- **Debian packaging first**: easy installation through a `.deb` package

## Current scope

The current version supports:

- local filesystem sources
- local backup destinations
- periodic scan-based backup cycles
- optional gzip compression
- per-file retention

The current version does **not** provide:

- real-time filesystem watching
- remote destinations
- deduplication
- block-level incremental backup
- snapshot-style restore tooling

## How it works

quiet-backup keeps a JSON state file, by default:

`/var/lib/quiet-backup/state.json`

For each tracked file, the daemon records enough metadata to know whether the file has changed since the last known backup state. During each cycle, it scans the configured patterns, collects files that should be backed up, then copies them gradually according to the configured rate limits.

Two mechanisms are used to reduce system impact:

1. a small pause between filesystem scan operations
2. a delay between file copies so backup work is spread over time

This makes quiet-backup closer to a “gentle background copy service” than to a traditional burst-mode backup tool.

## Installation

### Build the package

From the project root:

```bash
cd quiet-backup
./build.sh
```

This runs `dpkg-buildpackage` and moves the generated package files to `build`.

### Install the package

```bash
cd ../build
sudo apt install ./quiet-backup_*.deb
```

## Service setup

The package creates:

- a system user: `quiet-backup`
- a system group: `quiet-backup`
- a configuration file: `/etc/quiet-backup/config.json`
- a state directory: `/var/lib/quiet-backup`
- a backup directory: `/var/lib/quiet-backup/backups`
- a state file: `/var/lib/quiet-backup/state.json`

The service is installed but not automatically started, because it is mandatory to configure the files and directory you want to backup, and the choosen destination paths.

Enable and start it manually:

```bash
sudo systemctl enable quiet-backup
sudo systemctl start quiet-backup
```

Check status:

```bash
systemctl status quiet-backup
journalctl -u quiet-backup -f
```

## Configuration

The default configuration file is:

```text
/etc/quiet-backup/config.json
```

Example:

```json
{
  "state_file": "/var/lib/quiet-backup/state.json",
  "scan_pause_ms": 100,
  "min_interval_hours": 12,
  "spread_hours": 6,
  "max_files_per_minute": 1,
  "initial_delay_minutes": 10,
  "patterns": [
    {
      "name": "example-documents",
      "paths": [
        {
          "base": "/home/user/Documents", 
          "search": "*.pdf",
		  "ignore": ["**/venv/**"],
          "dest": "Documents"
        }
      ],
      "global_ignore": ["**/.directory"],
      "backup_policy": {
        "min_delay_before_backup": 2,
        "max_backups_per_file": 5,
        "compress": true,
        "compression_level": 6,
        "compress_ignore_filetype": [
          "zip", "gz", "tar", "bz2",
          "jpg", "jpeg", "png", "gif",
          "mp3", "mp4", "ogg", "avi",
          "mkv", "aac", "m4a", "flac"
        ]
      },
      "destinations": [
        {
          "type": "local",
          "path": "/var/lib/quiet-backup/backups"
        }
      ]
    }
  ]
}
```

## Configuration reference

### Global settings

#### `state_file`
Path to the JSON state file used to track known files.

#### `scan_pause_ms`
Pause in milliseconds between scan operations. Increase this if filesystem traversal should be more discreet.

#### `min_interval_hours`
Minimum delay between two full backup cycles.

#### `spread_hours`
Target duration over which the pending backup work should be spread.

#### `max_files_per_minute`
Upper limit for backup throughput. This prevents large bursts of copy activity.

#### `initial_delay_minutes`
Delay before the first backup cycle after service start.

#### `global_ignore`
A glob pattern to exclude files used for all pattern groups

### Pattern groups

Each item in `patterns` defines one backup group.

#### `name`
Logical name of the group. Used as a key in the state file.

#### `paths`
List of source path rules.

Each rule contains:

- `base`: base directory to scan
- `search`: glob pattern to match files
- `ignore`: glob pattern to exclude files
- `dest`: destination subdirectory name

#### `backup_policy`

- `min_delay_before_backup`: minimum age in hours before a changed file is backed up
- `max_backups_per_file`: number of versions to keep per file
- `compress`: whether to gzip the backup
- `compression_level`: gzip compression level
- `compress_ignore_filetype`: extensions that should not be compressed

#### `destinations`

Currently supported:

- `type: local`

Fields:

- `path`: base destination directory

## Backup naming and retention

When `max_backups_per_file` is greater than `1`, quiet-backup prefixes backup filenames with a UTC timestamp so several versions can coexist.

When `max_backups_per_file` is `1`, the latest backup replaces the previous one for that file path.

If compression is enabled, `.gz` is appended to the backup filename.

## Command line usage

The installed command is:

```bash
/usr/bin/quiet-backup
```

Typical usage:

```bash
quiet-backup --config /etc/quiet-backup/config.json
```

Useful options:

```bash
quiet-backup --config /etc/quiet-backup/config.json --run-once
quiet-backup --config /etc/quiet-backup/config.json --log-level debug
quiet-backup --config /etc/quiet-backup/config.json --max-files-per-minute 2
quiet-backup --config /etc/quiet-backup/config.json --scan-pause-ms 250
```

Available CLI options:

- `--config`
- `--state-file`
- `--min-interval-hours`
- `--spread-hours`
- `--initial-delay-minutes`
- `--scan-pause-ms`
- `--max-files-per-minute`
- `--run-once`
- `--log-level`

## Permissions and operational notes

quiet-backup runs as the `quiet-backup` system user.

This means source files must be readable by that user, and destination directories must be writable by that user. Before using paths in `/home/...`, make sure your permissions model actually allows access.

In practice, this daemon is easiest to use on:

- shared readable directories
- dedicated export directories
- application data directories with explicit access
- paths staged specifically for backup

### Simple setup with your current user's group

For a simple local setup, you can add the primary group of your current user to the `quiet-backup` user.

First, find your current primary group:

```bash
id -gn
```

Then add that group to the `quiet-backup` user:

```bash
sudo usermod -aG "$(id -gn)" quiet-backup
```

You can verify it with:

```bash
id quiet-backup
groups quiet-backup
```

After that, make sure the directories you want to back up are readable by your user group.

For example, if your files are already owned by your user and group, this may be enough for a simple setup.
## Example workflow

1. Install the package
2. Edit `/etc/quiet-backup/config.json`
3. Verify source read permissions
4. Start the service
5. Watch logs with `journalctl`
6. Tune `scan_pause_ms`, `spread_hours`, and `max_files_per_minute`

A good way to test safely is to launch one manual cycle first:

```bash
quiet-backup --config /etc/quiet-backup/config.json --run-once --initial-delay-minutes 0 --max-files-per-minute 60 --scan-pause-ms 10 --log-level debug
```

## Limitations

quiet-backup currently uses periodic scans, not filesystem events.

It detects file changes from metadata stored in the state file. It is therefore intentionally simple, but also less sophisticated than tools built around snapshots, hashing, deduplication or native incremental backup formats.

This project should be seen as a lightweight, configurable background backup helper for local filesystems.

## Development

### Build

```bash
./build.sh
```

### Source layout

- `main.py`: service lifecycle
- `config.py`: argument parsing and config overrides
- `backup.py`: scan and copy engine

### Debian packaging

The Debian packaging directory contains:

- package metadata in `control`
- file installation rules in `install`
- system user and state initialization in `postinst`
- systemd unit integration in `quiet-backup.service`

## Roadmap ideas

Possible next steps for the project:

- support remote destinations
- add restore helper commands
- add config validation
- improve retention policies
- add hashing for stronger change detection

## License

This project is under GPL-3.0 license