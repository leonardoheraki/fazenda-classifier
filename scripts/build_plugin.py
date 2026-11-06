"""Build a QGIS installable ZIP from the tracked plugin source directory."""
import configparser
import re
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "fazenda_classifier"
    config = configparser.ConfigParser(interpolation=None)
    config.read(source / "metadata.txt", encoding="utf-8")
    version = config["general"]["version"]
    if not re.fullmatch(r"[0-9A-Za-z._-]+", version):
        raise ValueError("Invalid version for a package filename")
    output = root / "dist" / f"fazenda_classifier_{version}.zip"
    output.parent.mkdir(exist_ok=True)
    files = [p for p in sorted(source.rglob("*")) if p.is_file()
             and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    forbidden = {".pth", ".pt", ".onnx", ".dll", ".so", ".zip", ".tif", ".tiff", ".gpkg"}
    if any(p.suffix.lower() in forbidden for p in files):
        raise ValueError("External weights, binaries, datasets and nested archives must not be bundled")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Package CRC validation failed")
    if output.stat().st_size > 25_000_000:
        raise ValueError("Package exceeds the QGIS repository's 25 MB limit")
    print(output)
    missing = [name for name in ("homepage", "repository", "tracker")
               if not config["general"].get(name, "").strip()]
    if missing:
        print("Before QGIS publication, fill metadata links: " + ", ".join(missing))


if __name__ == "__main__":
    main()
