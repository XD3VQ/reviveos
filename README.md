# ReviveOS — Our Development Experience

## Our Idea and Challenges

Building ReviveOS was a fun and challenging experience. Throughout development, we encountered several problems, especially when trying to make our application boot and function properly on both Windows and Linux. This was one of our biggest initial challenges.

Our main goal was to create a simple, easy-to-use application that wouldn't leave users confused or lost during the process of choosing and installing an operating system.

We also wanted ReviveOS to help users recover from operating system failures. For example, if someone's Linux installation became corrupted or their computer could no longer boot, they could plug in a ReviveOS USB drive and launch a temporary Debian-based environment.

From there, our vision was to let users recover their previous operating system, install a different one, or restart the installation process. We also explored the possibility of storing multiple operating systems directly on the USB drive, allowing users to choose between them without having to download everything again.

## Hardware Detection Challenges

Our second major challenge was accurately detecting computer specifications.

Since ReviveOS recommends operating systems based on the user's hardware and preferences, getting accurate information about the CPU, RAM, storage, and other components was essential.

We found that some methods of retrieving hardware information weren't always reliable across different operating systems.

We wanted to minimize external dependencies and avoid requiring users to install additional applications just to make ReviveOS work.

This pushed us to explore different approaches to hardware detection and improve how our backend handled system information.

## How We Divided the Work

**Sharan — Hardware Analysis and User Preferences**

Sharan mainly worked on hardware analysis, user preferences, and parts of the frontend. This involved making sure ReviveOS could collect system specifications and understand what users wanted from their computers.

**Ryan — OS Recommendations and Installation Assistance**

Ryan mainly worked on operating system recommendations, installation assistance, and backup-related functionality. His focus was connecting these features so users could move through the process smoothly.

## Technologies and What We Learned

Most of ReviveOS was developed using Flask, Python, JavaScript, HTML, and CSS.

Flask was relatively new to both of us, so working on this project helped us understand how frontend and backend systems communicate.

We learned more about Python functions, JavaScript, API endpoints, and how different parts of an application connect together.

We also used AI tools during development, particularly to speed up frontend development and help with repetitive code. We reviewed and supervised the generated output while working on our application.

## Final Reflection

ReviveOS helped us understand that building software isn't just about writing code. It also involves designing the user experience, solving compatibility problems, testing functionality, and making different systems work together.

Although we encountered several challenges, the project gave us experience with technologies we were still learning and helped us better understand the process of developing a complete application.

Our overall goal with ReviveOS was to make older computers useful again by simplifying operating system selection, installation, and recovery.

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
|-- requirements-dev.txt       Runtime dependencies plus PyInstaller
```
