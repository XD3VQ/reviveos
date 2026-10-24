"""Opt-in downloads from fixed publishers; never accept a user-provided URL."""
import hashlib
import re
import secrets
import shutil
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from .backup import checked_path


class DownloadError(ValueError):
    pass


PROVIDERS = {
    "linux-mint": {"base": "https://pub.linuxmint.io/stable/22.3/", "manifest": "sha256sum.txt", "pattern": r"linuxmint-22\.3-cinnamon-64bit\.iso", "guide": "https://linuxmint-installation-guide.readthedocs.io/en/latest/verify.html"},
    "debian": {"base": "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/", "manifest": "SHA256SUMS", "pattern": r"debian-13\.[0-9]+\.[0-9]+-amd64-netinst\.iso", "guide": "https://www.debian.org/CD/verify"},
}
MAX_DOWNLOAD_BYTES = 8 * 1024**3


class PublisherRedirects(HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != self.host or parsed.username or parsed.password:
            raise DownloadError("Redirect left the trusted HTTPS publisher host. Use manual instructions.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_publisher(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {urlsplit(item["base"]).hostname for item in PROVIDERS.values()}:
        raise DownloadError("Unapproved image source.")
    return build_opener(PublisherRedirects(parsed.hostname)).open(Request(url, headers={"User-Agent": "ReviveOS/0.3"}), timeout=15)


def resolve_image(os_id: str) -> dict:
    provider = PROVIDERS.get(os_id)
    if not provider:
        raise DownloadError("Automatic download is not configured for this OS. Follow its official download instructions.")
    with open_publisher(provider["base"] + provider["manifest"]) as response:
        text = response.read(128 * 1024 + 1)
    if len(text) > 128 * 1024:
        raise DownloadError("Checksum manifest exceeds the allowed size.")
    matches = []
    for line in text.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^/\\]+)", line.strip())
        if match and re.fullmatch(provider["pattern"], match[2]):
            matches.append((match[1].lower(), match[2]))
    if len(matches) != 1:
        raise DownloadError("No unique image for the selected OS version in the publisher manifest. Use manual instructions.")
    checksum, filename = matches[0]
    return {"os_id": os_id, "filename": filename, "sha256": checksum,
            "url": provider["base"] + filename, "manifest_url": provider["base"] + provider["manifest"],
            "verification_guide": provider["guide"], "signature_status": "not_verified"}


def download_image(os_id: str, destination: str, update=lambda **values: None) -> dict:
    """Stream bounded bytes into a new folder and compare the HTTPS checksum.

    This is integrity checking, not OpenPGP signature authentication. Partial
    output is retained and labelled unusable; existing files are never replaced.
    """
    update(phase="destination", message="Checking your download folder…")
    target = checked_path(destination)
    if not target.is_dir():
        raise DownloadError("Choose an existing destination directory.")
    update(phase="publisher", message="Checking the official download site and file information…")
    image = resolve_image(os_id)
    folder = target / ("ReviveOS-download-" + secrets.token_hex(8))
    folder.mkdir(exist_ok=False)
    output_path = folder / (image["filename"] + ".unverified")
    digest, size = hashlib.sha256(), 0
    start = time.monotonic()
    try:
        update(phase="connecting", message="Connecting to the official installer download…")
        with open_publisher(image["url"]) as response, output_path.open("xb") as output:
            length = response.headers.get("Content-Length")
            expected_size = int(length) if length is not None else None
            if expected_size is not None and (expected_size <= 0 or expected_size > MAX_DOWNLOAD_BYTES):
                raise DownloadError("Publisher image size is outside the allowed range.")
            required_space = expected_size if expected_size is not None else MAX_DOWNLOAD_BYTES
            if shutil.disk_usage(target).free < required_space + 16 * 1024**2:
                raise DownloadError("Destination has insufficient free space.")
            update(phase="downloading", message="Downloading the installer…", bytes_downloaded=0, total_bytes=expected_size)
            while chunk := response.read(1024**2):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES or time.monotonic() - start > 2 * 60 * 60:
                    raise DownloadError("Download exceeded the 8 GiB or two-hour limit.")
                output.write(chunk)
                digest.update(chunk)
                update(phase="downloading", message="Downloading the installer…", bytes_downloaded=size, total_bytes=expected_size)
        update(phase="verifying", message="Checking that the downloaded file is complete…", bytes_downloaded=size, total_bytes=expected_size)
        if not size or (expected_size is not None and size != expected_size):
            raise DownloadError("Incomplete image transfer.")
        if digest.hexdigest() != image["sha256"]:
            raise DownloadError("SHA-256 mismatch. Do not use this image.")
    except Exception as error:
        raise DownloadError(f"Download failed: {error}. Incomplete output retained in {folder}; do not use it.") from error
    return {**image, "path": str(output_path), "bytes": size, "integrity": "sha256_match",
            "signature_status": "not_verified", "ready_to_boot": False,
            "message": "Checksum matches the publisher HTTPS manifest. Verify the publisher signature using the official guide before renaming the file to .iso and using it."}
