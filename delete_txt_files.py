import os
import sys
from pathlib import Path

def delete_txt(target: Path, dry_run: bool = False):
    if not target.exists() or not target.is_dir():
        print(f"Directory not found: {target}")
        return 1
    txt_files = [p for p in target.iterdir() if p.is_file() and p.suffix.lower() == '.txt']
    if not txt_files:
        print("No .txt files found.")
        return 0
    print(f"Found {len(txt_files)} .txt files in {target}:")
    for f in txt_files:
        print("  -", f.name)
    if dry_run:
        print("Dry run: nothing deleted.")
        return 0
    # Simple confirmation (skip if --yes)
    if '--yes' not in sys.argv:
        ans = input('Delete all listed files? (y/N): ').strip().lower()
        if ans != 'y':
            print('Aborted.')
            return 0
    deleted = 0
    for f in txt_files:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            print(f"Failed to delete {f.name}: {e}")
    print(f"Deleted {deleted} / {len(txt_files)} files.")
    return 0

if __name__ == '__main__':
    # Usage: python delete_txt_files.py [path] [--dry-run] [--yes]
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    path = Path(args[0]) if args else Path('.')
    dry = '--dry-run' in sys.argv
    sys.exit(delete_txt(path, dry_run=dry))
