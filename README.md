# ReviveOS

ReviveOS is a local web application that helps people assess an older computer, compare operating systems, back up files, and prepare for a manual installation. The same Flask backend and browser interface run on Windows, Linux, and a bootable Debian live environment.

The current recommendation catalog covers Linux. Windows preferences are available, but Windows compatibility checks are referred to Microsoft's official tools. No paid API key is required.

## What it does

- Detects hardware on the computer running the backend, including CPU, memory, system-filesystem storage, architecture, and available TPM information.
- Offers optional CPU, memory-copy, and read-only file benchmarks.
- Ranks operating systems using preferences, application compatibility, and JSON catalog requirements. Known failures and unverified checks remain visible.
- Lets you compare recommendations and keep up to two installation options.
- Prepares file backups and verifies copied files, with explicit consent.
- Provides official download links, supported image downloads with SHA-256 checks, and installation guidance.
- Offers an optional local AI assistant for explanations and preference drafts that you review and save.

Hardware detection, questionnaires, and catalog-based recommendations work offline. Image downloads and initial AI model downloads need internet access.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\launch-reviveos.bat
```

After setup, you can double-click `launch-reviveos.bat` to start the app.

### Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sh launch-reviveos.sh


## Use the application

1. Start at **Welcome** and confirm whether a working OS is already installed.
2. Open **User Preferences** and choose your usage, experience, OS comfort, and essential applications.
3. Run **Hardware Analysis**, then optionally run the benchmarks.
4. Compare **OS Recommendations**, review evidence gaps, and select your shortlist.
5. In **Installation**, prepare and confirm your backup, then approve a supported download or use an official download link.
6. Follow the handoff instructions to create installation media and install the OS yourself.

Preferences are saved for the browser session. Hardware results describe the backend host; inside a VM, they describe the VM. Scores are ranking points, not compatibility probabilities or speed guarantees. Planning estimates are separate from verified requirements.

ReviveOS does not format drives, change partitions, install an OS, or reboot automatically. File backups are not complete system recovery images. A matching download checksum does not authenticate a publisher signature; signature verification remains a manual step. Graphics, Wi-Fi, firmware, and boot support require device-specific checks.

## Project structure

```text
reviveos/
|-- app.py                     Flask application factory and core API routes
|-- config.py                  Local server and catalog configuration
|-- launch.py                  Browser/server launcher and worker dispatch
|-- launch-reviveos.bat         Windows source launcher
|-- launch-reviveos.sh          Linux source launcher
|-- backend/
|   |-- hardware.py            Hardware detection and CPU/TPM information
|   |-- environment.py         Running environment and mounted destinations
|   |-- analysis.py            Benchmark coordination and result lifetime
|   |-- benchmark.py           Benchmark process management
|   |-- benchmark_worker.py    CPU, memory, and file-read measurements
|   |-- catalog.py             Catalog loading and validation
|   |-- compatibility.py       OS and application compatibility checks
|   |-- recommender.py         Ranking, explanations, and planning estimates
|   |-- backup.py              Backup inspection and verified file copying
|   |-- downloads.py           Supported publisher downloads and checksums
|   |-- installer.py           Manual installation guidance
|   |-- routes.py              Workflow and optional AI API routes
|   |-- tasks.py               Background task management
|   |-- local_ai.py            Loopback-only Ollama integration
|   |-- path_picker.py         Native file and folder dialogs
|   `-- runtime.py             Worker command selection
|-- templates/index.html       Shared browser interface
|-- static/                    JavaScript behavior and CSS
|-- data/                      OS, application, and CPU JSON catalogs
|-- bootable/                  Debian live image builder and boot checks
|-- tools/                     Windows packaging and local AI preparation
|-- requirements.txt           Flask and psutil runtime dependencies
`-- requirements-dev.txt       Runtime dependencies plus PyInstaller
```


## Build a bootable Linux ISO

Use a disposable Debian 13 amd64 build VM with at least 20 GB of free space:


## Check application changes

There is no general automated application test suite in the current tree. Launch the app and exercise the affected screens: save preferences, detect hardware, run optional benchmarks, compare results, and check the installation handoff. Use disposable sample files for backup checks and distinguish demo downloads from real downloads. The `bootable/` scripts provide separate live-image startup and VM checks.
