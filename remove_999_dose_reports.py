import argparse
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pydicom
from pydicom.uid import ExplicitVRLittleEndian

# remove_999_dose_reports.py
#
# Purpose:
#   Post-process an already de-identified dataset and crop the top quarter of
#   SeriesNumber=999 dose-report DICOM images.
#
# Default behavior:
#   Copy mode (safe): writes to --output and leaves --input unchanged.
#
# Required args:
#   --input PATH                 Root directory to scan.
#
# Copy mode args (default):
#   --output PATH                Destination for cleaned copy.
#
# In-place mode args:
#   --in-place                   Modify files directly in --input.
#
# Optional args:
#   --workers N                  Parallel worker threads (default: auto).
#   --dry-run                    Preview actions without writing changes.
#   --no-progress                Disable live progress line.
#
# Note:
#   Some dose-report DICOMs are compressed and require an installed pixel
#   decoder backend (e.g., pylibjpeg or GDCM) to access pixel_array.
#   If cropping fails for Series 999, the script exits non-zero.
#
# Examples:
#   python remove_999_dose_reports.py --input ./old_deid_output --output ./cleaned
#   python remove_999_dose_reports.py --input ./old_deid_output --in-place


def _normalize_value(value):
    if value is None:
        return None
    value_str = str(value).strip()
    if len(value_str) >= 5 and all(c == "_" for c in value_str):
        return None
    return value_str if value_str else None


def _is_999_dose_report(ds):
    """Return True when a DICOM object is the Series 999 dose report."""
    series_number = _normalize_value(getattr(ds, "SeriesNumber", None))
    return series_number == "999"


def _setup_log(log_root):
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / f"dose_report_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("Timestamp,File,SeriesNumber,Action,Status,Details\n")
    return log_path


def _log_event(log_path, file_path, series_number, action, status, details=""):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            f"{datetime.now().isoformat()},{file_path},{series_number},{action},{status},{details}\n"
        )


def _copy_file(source_root, output_root, file_path):
    rel_path = file_path.relative_to(source_root)
    target = output_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file_path, target)


def _process_file(file_path, input_root, output_root, in_place, dry_run):
    rel_path = file_path.relative_to(input_root)
    stats = {
        "total_files": 1,
        "dicom_files": 0,
        "cropped_999": 0,
        "failed_999": 0,
        "kept_dicom": 0,
        "copied_non_dicom": 0,
        "errors": 0,
    }

    if file_path.suffix.lower() != ".dcm":
        if output_root and not dry_run:
            _copy_file(input_root, output_root, file_path)
        if output_root:
            stats["copied_non_dicom"] += 1
        return stats, None

    stats["dicom_files"] += 1

    try:
        ds = pydicom.dcmread(str(file_path))
        series_number = _normalize_value(getattr(ds, "SeriesNumber", "")) or "N/A"

        if _is_999_dose_report(ds):
            crop_rows = _crop_top_quarter(ds)
            stats["cropped_999"] += 1

            target_path = file_path if in_place else output_root / rel_path
            if not dry_run:
                if not in_place:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                _write_dicom(ds, target_path)

            return (
                stats,
                {
                    "file": str(rel_path),
                    "series": series_number,
                    "action": "CROP_TOP_QUARTER",
                    "status": "SERIES_999_DOSE_REPORT",
                    "details": f"removed_rows={crop_rows}",
                },
            )

        stats["kept_dicom"] += 1
        if output_root and not dry_run:
            _copy_file(input_root, output_root, file_path)

        return (
            stats,
            {
                "file": str(rel_path),
                "series": series_number,
                "action": "KEEP",
                "status": "OK",
                "details": "",
            },
        )

    except Exception as exc:
        stats["errors"] += 1
        is_999 = False
        try:
            ds_header = pydicom.dcmread(str(file_path), stop_before_pixels=True)
            is_999 = _is_999_dose_report(ds_header)
        except Exception:
            is_999 = False

        if is_999:
            stats["failed_999"] += 1
        elif output_root and not dry_run:
            # Keep non-999 files on error so data is not dropped unexpectedly.
            _copy_file(input_root, output_root, file_path)

        return (
            stats,
            {
                "file": str(rel_path),
                "series": "N/A",
                "action": "ERROR",
                "status": "CROP_FAILED_999" if is_999 else "READ_FAILED",
                "details": str(exc).replace(",", ";"),
            },
        )


def _write_dicom(ds, target_path):
    # Force an uncompressed transfer syntax to safely persist edited pixel data.
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(str(target_path), write_like_original=False)


def _crop_top_quarter(ds):
    """Crop out the top 25% of image rows and update Rows/PixelData."""
    if not hasattr(ds, "PixelData") or not hasattr(ds, "Rows"):
        raise ValueError("No pixel data available")

    pixel_array = ds.pixel_array
    rows = int(ds.Rows)
    crop_rows = rows // 4

    if crop_rows <= 0:
        return 0

    number_of_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
    samples_per_pixel = int(getattr(ds, "SamplesPerPixel", 1) or 1)

    if pixel_array.ndim == 2:
        cropped = pixel_array[crop_rows:, :]
    elif pixel_array.ndim == 3:
        if number_of_frames > 1:
            cropped = pixel_array[:, crop_rows:, :]
        elif samples_per_pixel > 1:
            cropped = pixel_array[crop_rows:, :, :]
        else:
            cropped = pixel_array[:, crop_rows:, :]
    elif pixel_array.ndim == 4:
        cropped = pixel_array[:, crop_rows:, :, :]
    else:
        raise ValueError(f"Unsupported pixel array shape: {pixel_array.shape}")

    ds.Rows = rows - crop_rows
    ds.PixelData = cropped.tobytes()

    # Remove potentially stale derived values if present.
    for keyword in ["SmallestImagePixelValue", "LargestImagePixelValue"]:
        if keyword in ds:
            del ds[keyword]

    return crop_rows


def _print_progress(processed, total, start_time):
    if total <= 0:
        return
    elapsed = max(time.time() - start_time, 1e-9)
    pct = (processed / total) * 100
    rate = processed / elapsed
    print(
        f"\rProgress: {processed}/{total} ({pct:5.1f}%) | {rate:6.1f} files/s | elapsed {elapsed:6.1f}s",
        end="",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Crop the top quarter of SeriesNumber=999 dose-report DICOM images in an already de-identified dataset."
        )
    )
    parser.add_argument("--input", required=True, help="Directory to clean")
    parser.add_argument(
        "--output",
        help="Output directory for cleaned copy (required unless --in-place is used)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify matching files directly in --input instead of writing a copied dataset",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be cropped/copied without changing files",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(32, (os.cpu_count() or 4) * 2)),
        help="Number of parallel worker threads (default: auto)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable live progress indicator",
    )
    args = parser.parse_args()

    input_root = Path(args.input)
    if not input_root.exists() or not input_root.is_dir():
        raise ValueError(f"Input directory does not exist: {input_root}")

    if args.in_place and args.output:
        raise ValueError("Use either --in-place or --output, not both")

    if not args.in_place and not args.output:
        raise ValueError("--output is required when --in-place is not used")

    output_root = Path(args.output) if args.output else None
    if output_root and output_root.resolve() == input_root.resolve():
        raise ValueError("--output must be different from --input")

    if args.workers < 1:
        raise ValueError("--workers must be >= 1")

    log_root = input_root if args.in_place else output_root
    log_path = _setup_log(log_root)

    stats = {
        "total_files": 0,
        "dicom_files": 0,
        "cropped_999": 0,
        "failed_999": 0,
        "kept_dicom": 0,
        "copied_non_dicom": 0,
        "errors": 0,
    }

    start_time = time.time()

    all_files = [Path(root) / filename for root, _, files in os.walk(input_root) for filename in files]
    total_files = len(all_files)
    processed_files = 0
    last_progress_ts = 0.0

    if total_files > 0 and not args.no_progress:
        _print_progress(0, total_files, start_time)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                _process_file,
                file_path,
                input_root,
                output_root,
                args.in_place,
                args.dry_run,
            )
            for file_path in all_files
        ]

        for future in as_completed(futures):
            file_stats, log_entry = future.result()
            processed_files += 1

            for key, value in file_stats.items():
                stats[key] += value

            if log_entry:
                _log_event(
                    log_path,
                    log_entry["file"],
                    log_entry["series"],
                    log_entry["action"],
                    log_entry["status"],
                    log_entry["details"],
                )

            if not args.no_progress:
                now = time.time()
                if processed_files == total_files or now - last_progress_ts >= 0.5:
                    _print_progress(processed_files, total_files, start_time)
                    last_progress_ts = now

    if total_files > 0 and not args.no_progress:
        print()

    elapsed = time.time() - start_time

    print("\n--- Dose Report Cropping Summary ---")
    print(f"Input Directory:      {input_root}")
    if output_root:
        print(f"Output Directory:     {output_root}")
    print(f"Mode:                 {'in-place' if args.in_place else 'copy'}")
    print(f"Dry Run:              {args.dry_run}")
    print(f"Worker Threads:       {args.workers}")
    print(f"Total Files Seen:     {stats['total_files']}")
    print(f"DICOM Files Seen:     {stats['dicom_files']}")
    print(f"Series 999 Cropped:   {stats['cropped_999']}")
    print(f"Series 999 Failed:    {stats['failed_999']}")
    print(f"DICOM Files Kept:     {stats['kept_dicom']}")
    if output_root:
        print(f"Non-DICOM Files Copied: {stats['copied_non_dicom']}")
    print(f"Errors:               {stats['errors']}")
    print(f"Log File:             {log_path}")
    print(f"Elapsed Time:         {elapsed:.2f} seconds")
    print("-----------------------------------")

    if stats["failed_999"] > 0:
        print("WARNING: Some Series 999 files could not be cropped.")
        print("Install a pixel decoder and rerun (e.g. pip install pylibjpeg pylibjpeg-libjpeg).")
        print("Those failed 999 files were NOT copied to output in copy mode.")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
