#!/usr/bin/env python3
"""
FishCam Data Deletion Utility

Deletes all files in the data directories defined in fishcam_config.yaml
(video, logs, IMU, GPS). The directory structure is preserved.

Usage (from the scripts directory):
    python3 delete_data.py
"""

from pathlib import Path
import config


def count_files(directories):
    """Return total file count and total size (bytes) across all directories."""
    total_files = 0
    total_bytes = 0
    for d in directories:
        if d.exists():
            for f in d.rglob('*'):
                if f.is_file():
                    total_files += 1
                    total_bytes += f.stat().st_size
    return total_files, total_bytes


def fmt_size(total_bytes):
    """Format byte count as human-readable string."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if total_bytes < 1024:
            return f'{total_bytes:.1f} {unit}'
        total_bytes /= 1024
    return f'{total_bytes:.1f} TB'


def main():
    paths = config.get_paths()
    base  = Path(__file__).parent

    directories = {
        'Video' : base / paths['video_dir'],
        'Logs'  : base / paths['log_dir'],
        'IMU'   : base / paths['imu_dir'],
        'GPS'   : base / paths['gps_dir'],
    }

    print('=' * 60)
    print('FishCam Data Deletion Utility')
    print('=' * 60)
    print()
    print('Directories that will be cleared:')
    for label, path in directories.items():
        exists = path.exists()
        print(f'  [{label}] {path}', '(not found)' if not exists else '')

    print()

    all_dirs = list(directories.values())
    total_files, total_bytes = count_files(all_dirs)

    if total_files == 0:
        print('No files found — nothing to delete.')
        return

    print(f'Found {total_files} file(s) totalling {fmt_size(total_bytes)}.')
    print()
    print('WARNING: This action is irreversible.')
    print('Type "DELETE ALL" to confirm: ', end='', flush=True)

    confirmation = input().strip()
    if confirmation != 'DELETE ALL':
        print('Aborted — no files were deleted.')
        return

    print()
    deleted_files = 0
    failed_files  = 0

    for label, directory in directories.items():
        if not directory.exists():
            print(f'  [{label}] skipped (directory not found)')
            continue

        files = [f for f in directory.rglob('*') if f.is_file()]
        if not files:
            print(f'  [{label}] empty — nothing to delete')
            continue

        print(f'  [{label}] deleting {len(files)} file(s)...')
        for f in files:
            try:
                f.unlink()
                deleted_files += 1
            except Exception as e:
                print(f'    ERROR deleting {f.name}: {e}')
                failed_files += 1

        # Remove empty subdirectories (but keep the top-level data dir)
        for d in sorted(directory.rglob('*'), reverse=True):
            if d.is_dir():
                try:
                    d.rmdir()  # only succeeds if empty
                except OSError:
                    pass  # not empty, leave it

    print()
    print(f'Done — {deleted_files} file(s) deleted.', end='')
    if failed_files:
        print(f' {failed_files} file(s) could not be deleted (see errors above).', end='')
    print()


if __name__ == '__main__':
    main()
