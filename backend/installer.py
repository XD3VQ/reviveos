"""Developer B: read-only preparation and manual installation handoff."""

INSTALLATION_SOURCES = {
    "linux-mint": {"download": "https://www.linuxmint.com/edition.php?id=326", "verify": "https://linuxmint-installation-guide.readthedocs.io/en/latest/verify.html", "install": "https://linuxmint-installation-guide.readthedocs.io/en/latest/", "automatic_download": True},
    "debian": {"download": "https://www.debian.org/distrib/netinst", "verify": "https://www.debian.org/CD/verify", "install": "https://www.debian.org/releases/trixie/amd64/", "automatic_download": True},
    "lubuntu": {"download": "https://lubuntu.me/downloads/", "verify": "https://ubuntu.com/tutorials/how-to-verify-ubuntu", "install": "https://manual.lubuntu.me/lts/1/Installing_lubuntu.html", "automatic_download": False},
}

def prepare_installation(os_id: str, operating_system: dict | None = None) -> dict:
    """Return actual links and a checklist without modifying boot settings/devices."""
    links = INSTALLATION_SOURCES.get(os_id)
    if links is None:
        if operating_system is None or operating_system.get("id") != os_id:
            raise ValueError("Unknown OS selection.")
        supplied = operating_system.get("installation", {})
        fallback = operating_system["sources"][0]["url"]
        links = {"download": supplied.get("download") or fallback, "verify": supplied.get("verification") or fallback,
                 "install": supplied.get("installation") or fallback, "automatic_download": False}
    return {"os_id": os_id, "status": "preparation_only", **links,
            "usb_methods": [{"id": "rufus", "name": "Rufus (Windows, manual)", "url": "https://rufus.ie/en/"},
                            {"id": "manual", "name": "Official OS USB instructions (manual)", "url": links["install"]}],
            "checklist": ["Back up important files to a separate physical drive and open a few copied files.",
                          "Obtain the image from the publisher and verify its signed checksums.",
                          "Identify a spare USB by model/capacity and back up its contents.",
                          "Use Rufus or official OS instructions yourself. Creating media erases the selected USB; ReviveOS does not write it.",
                          "Keep recovery media and disk-encryption recovery keys separately.",
                          "Boot the USB through the one-time boot menu, test hardware, and follow the normal OS installer."],
            "warnings": ["Do not use the backup drive as the installer USB.",
                         "Debian automatic download uses its non-live net installer; network access is needed for a desktop. Choose Xfce during setup." if os_id == "debian" else "Review the selected release's official guide.",
                         "No automatic OS rollback exists. A file backup alone cannot restore the previous OS.",
                         "ReviveOS does not write USB media, change partitions, reboot, or perform installation."]}
