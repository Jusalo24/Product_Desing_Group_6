"""Stage the manually downloaded Fineli ZIP from the repository root.

Usage (from the backend folder):
    python -m app.scripts.download_fineli
    python -m app.scripts.download_fineli --output-dir data\\fineli
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from app.scripts.progress import ProgressBar

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_PATH = PROJECT_ROOT / "Fineli_Rel20__74_ravintotekij__.zip"
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "fineli"
REQUIRED_FILES = (
    "food.csv",
    "foodname_EN.csv",
    "component.csv",
    "eufdname_EN.csv",
    "cmpclass_EN.csv",
    "compunit_EN.csv",
    "component_value.csv",
    "foodaddunit.csv",
    "foodunit_EN.csv",
)


def stage_csv_files(
    archive_path: Path, output_dir: Path, show_progress: bool = False
) -> None:
    """Copy the required CSVs from an archive, including when they are nested."""
    with zipfile.ZipFile(archive_path) as archive:
        members: dict[str, zipfile.ZipInfo] = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename.replace("\\", "/")).name
            if name in REQUIRED_FILES:
                if name in members:
                    raise ValueError(f"Archive contains multiple files named {name}")
                members[name] = info

        missing = [name for name in REQUIRED_FILES if name not in members]
        if missing:
            raise FileNotFoundError(
                f"Fineli archive is missing required files: {', '.join(missing)}"
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".fineli-stage-", dir=output_dir) as staging:
            staging_dir = Path(staging)
            total_bytes = sum(members[name].file_size for name in REQUIRED_FILES)
            with ProgressBar("Staging Fineli files", total_bytes, show_progress) as progress:
                for name in REQUIRED_FILES:
                    with archive.open(members[name]) as source, (staging_dir / name).open("wb") as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
                            progress.advance(len(chunk))
            for name in REQUIRED_FILES:
                os.replace(staging_dir / name, output_dir / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()

    if not ARCHIVE_PATH.is_file():
        print(
            "Fineli's direct download is unavailable to this script. Download the "
            "Fineli Rel20 nutrient-data ZIP in your browser and move it to the "
            f"project root as:\n  {ARCHIVE_PATH}\nThen run this command again.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        stage_csv_files(ARCHIVE_PATH, args.output_dir, show_progress=True)
    except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Could not stage Fineli data from {ARCHIVE_PATH}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Staged Fineli CSV files in {args.output_dir}")


if __name__ == "__main__":
    main()
