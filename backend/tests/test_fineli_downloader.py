from io import BytesIO
from pathlib import Path
import sys
import zipfile

import pytest

from app.scripts.download_fineli import ARCHIVE_PATH, REQUIRED_FILES, main, stage_csv_files


def _create_archive(path: Path, nested: bool = True) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for filename in REQUIRED_FILES:
            member = f"fineli/package/{filename}" if nested else filename
            archive.writestr(member, f"contents of {filename}")
        archive.writestr("fineli/package/ignore.txt", "not required")


def test_cli_stages_root_archive_in_default_data_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive_path = tmp_path / ARCHIVE_PATH.name
    _create_archive(archive_path)
    output_dir = tmp_path / "backend" / "data" / "fineli"
    monkeypatch.setattr("app.scripts.download_fineli.ARCHIVE_PATH", archive_path)
    monkeypatch.setattr("app.scripts.download_fineli.DEFAULT_DIR", output_dir)
    monkeypatch.setattr(sys, "argv", ["app.scripts.download_fineli"])

    main()

    assert sorted(path.name for path in output_dir.iterdir()) == sorted(REQUIRED_FILES)
    for filename in REQUIRED_FILES:
        assert (output_dir / filename).read_text() == f"contents of {filename}"
    assert "Staging Fineli files: complete" in capsys.readouterr().err


def test_cli_explains_manual_download_and_root_location_when_archive_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    archive_path = tmp_path / ARCHIVE_PATH.name
    monkeypatch.setattr("app.scripts.download_fineli.ARCHIVE_PATH", archive_path)
    monkeypatch.setattr(sys, "argv", ["app.scripts.download_fineli"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    error = capsys.readouterr().err
    assert "Fineli Rel20 nutrient-data ZIP in your browser" in error
    assert str(archive_path) in error
    assert not (tmp_path / "backend" / "data" / "fineli").exists()


def test_cli_supports_custom_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / ARCHIVE_PATH.name
    _create_archive(archive_path)
    output_dir = tmp_path / "custom-data"
    monkeypatch.setattr("app.scripts.download_fineli.ARCHIVE_PATH", archive_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["app.scripts.download_fineli", "--output-dir", str(output_dir)],
    )

    main()

    assert sorted(path.name for path in output_dir.iterdir()) == sorted(REQUIRED_FILES)


def test_stage_reports_archive_missing_required_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("food.csv", "food data")

    with pytest.raises(FileNotFoundError, match="foodname_EN.csv"):
        stage_csv_files(archive_path, tmp_path / "output")


def test_stage_reports_missing_classification_file(tmp_path: Path) -> None:
    archive_path = tmp_path / "incomplete-classifications.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for filename in REQUIRED_FILES:
            if filename != "process_EN.csv":
                archive.writestr(filename, "data")

    with pytest.raises(FileNotFoundError, match="process_EN.csv"):
        stage_csv_files(archive_path, tmp_path / "output")


def test_stage_rejects_duplicate_required_file_names(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for filename in REQUIRED_FILES:
            archive.writestr(f"first/{filename}", "first version")
            if filename == "food.csv":
                archive.writestr(f"second/{filename}", "second version")

    with pytest.raises(ValueError, match="multiple files named food.csv"):
        stage_csv_files(archive_path, tmp_path / "output")

    assert not (tmp_path / "output").exists()


def test_corrupt_archive_does_not_replace_or_partially_stage_csvs(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "corrupt.zip"
    archive_bytes = BytesIO()
    _create_archive_in_memory(archive_bytes)
    corrupt_zip = archive_bytes.getvalue().replace(
        b"contents of foodname_EN.csv", b"corrupt! of foodname_EN.csv"
    )
    archive_path.write_bytes(corrupt_zip)
    existing_dir = tmp_path / "fineli"
    existing_dir.mkdir()
    (existing_dir / "food.csv").write_text("previous release")

    with pytest.raises(zipfile.BadZipFile):
        stage_csv_files(archive_path, existing_dir)

    assert (existing_dir / "food.csv").read_text() == "previous release"
    assert sorted(path.name for path in existing_dir.iterdir()) == ["food.csv"]


def _create_archive_in_memory(archive_bytes: BytesIO) -> None:
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        for filename in REQUIRED_FILES:
            archive.writestr(filename, f"contents of {filename}")
