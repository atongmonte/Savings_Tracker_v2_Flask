"""
Script to migrate files from old repository to new SavingsTrackerV2_testdev repository based on file_tracking table.

Steps:
1. Read all records from file_tracking table.
2. For each record, create a subfolder in the new repository named by initiative_id.
3. Search for the file by file_name in the old repository (search multiple locations).
4. Copy the file to the new initiative_id subfolder.
5. Update file_path, file_size, and file_type in the database.
"""

import os
import re
import sys
import argparse
import shutil
import unicodedata

# Ensure project root is in sys.path for module imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# CONFIGURATION: search both the legacy repo and the PMO folder
OLD_REPO = os.path.normpath(r'\\montefiore.org\\centralfiles\\data\\Procurement PMO\\SAVINGS_TRACKER_FILE_REPOSITORY - Copy')
NEW_REPO = os.path.normpath(r'\\montefiore.org\\centralfiles\\data\\Procurement PMO\\SavingsTrackerV2_testdev')

# If running standalone, set up Flask app context
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from app import create_app
app = create_app(os.getenv("FLASK_CONFIG", "testing"))


IGNORE_DIR_NAMES = {"node_modules", "__pycache__", "venv", ".git"}


def normalize_lookup_name(name):
    """Normalize a file name for resilient matching across repositories."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9._-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_lookup_keys(filename):
    """Return exact and normalized lookup keys for a filename."""
    filename = (filename or "").strip()
    stem = os.path.splitext(filename)[0]
    keys = [filename.lower(), normalize_lookup_name(filename)]
    if stem:
        keys.extend([stem.lower(), normalize_lookup_name(stem)])
    return [key for key in dict.fromkeys(keys) if key]


def build_file_index(search_roots):
    """Scan repository roots once and index files for fast matching."""
    file_index = {}
    total_files = 0

    for root in search_roots:
        root = os.path.normpath(root)
        if not os.path.exists(root):
            print(f"[WARN] Search root not available: {root}")
            continue

        print(f"[INDEX] Scanning repository: {root}")
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in IGNORE_DIR_NAMES]
            for file_name in files:
                full_path = os.path.normpath(os.path.join(current_root, file_name))
                total_files += 1
                for key in get_lookup_keys(file_name):
                    file_index.setdefault(key, []).append(full_path)

    print(f"[INDEX] Indexed {total_files} files across {len(search_roots)} repository roots.")
    return file_index


def choose_best_candidate(filename, candidates, initiative_id=None):
    """Pick the most likely file match using initiative and filename similarity."""
    if not candidates:
        return None

    wanted_name = (filename or "").lower()
    wanted_normalized = normalize_lookup_name(filename)
    wanted_stem = normalize_lookup_name(os.path.splitext(filename or "")[0])
    initiative_token = str(initiative_id) if initiative_id is not None else ""

    def _score(path):
        base_name = os.path.basename(path)
        base_normalized = normalize_lookup_name(base_name)
        base_stem = normalize_lookup_name(os.path.splitext(base_name)[0])

        score = 0
        if base_name.lower() == wanted_name:
            score += 120
        if base_normalized == wanted_normalized:
            score += 90
        if wanted_stem and base_stem == wanted_stem:
            score += 70
        if initiative_token and initiative_token in os.path.normpath(path):
            score += 40
        if os.path.normcase(path).startswith(os.path.normcase(NEW_REPO)):
            score += 20
        return score

    unique_candidates = list(dict.fromkeys(os.path.normpath(path) for path in candidates if os.path.isfile(path)))
    if not unique_candidates:
        return None
    return max(unique_candidates, key=_score)


def find_file(filename, search_roots, initiative_id=None, file_index=None):
    """Find a file anywhere in the configured repositories using robust matching."""
    if isinstance(search_roots, str):
        search_roots = [search_roots]

    for root in search_roots:
        if not os.path.exists(root):
            continue
        quick_try = os.path.normpath(os.path.join(root, filename))
        if os.path.isfile(quick_try):
            return quick_try

    candidates = []
    if file_index:
        for key in get_lookup_keys(filename):
            candidates.extend(file_index.get(key, []))

        if not candidates:
            target_stem = normalize_lookup_name(os.path.splitext(filename or "")[0])
            if target_stem:
                for key, paths in file_index.items():
                    if len(key) >= 8 and (key.startswith(target_stem) or target_stem.startswith(key)):
                        candidates.extend(paths)

        best_match = choose_best_candidate(filename, candidates, initiative_id=initiative_id)
        if best_match:
            return best_match

    fallback_normalized = normalize_lookup_name(filename)
    fallback_stem = normalize_lookup_name(os.path.splitext(filename or "")[0])
    for root in search_roots:
        if not os.path.exists(root):
            continue
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in IGNORE_DIR_NAMES]
            for file_name in files:
                normalized_name = normalize_lookup_name(file_name)
                normalized_stem = normalize_lookup_name(os.path.splitext(file_name)[0])
                if (
                    file_name.lower() == (filename or "").lower()
                    or normalized_name == fallback_normalized
                    or (fallback_stem and normalized_stem == fallback_stem)
                ):
                    return os.path.normpath(os.path.join(current_root, file_name))
    return None


def get_destination_path(initiative_id, filename):
    """Build the canonical destination path in the new repository."""
    return os.path.normpath(os.path.join(NEW_REPO, str(initiative_id), filename))


def update_file_tracking_record(record, actual_path, session, stored_path=None):
    """Update file_tracking metadata from an existing file or a newly copied file."""
    actual_path = os.path.normpath(actual_path)
    stored_path = os.path.normpath(stored_path or actual_path)
    record.file_path = stored_path
    try:
        record.file_size = os.path.getsize(actual_path)
    except OSError:
        record.file_size = None
    extension_source = os.path.basename(actual_path) or record.file_name
    record.file_type = os.path.splitext(extension_source)[1].lower().lstrip('.') or None
    session.add(record)


def clean_new_repository(repo_path, dry_run=False):
    """Remove all existing files/folders from the destination repository before a full reload."""
    repo_path = os.path.normpath(repo_path)
    repo_name = os.path.basename(repo_path.rstrip("\\/"))
    if repo_name.lower() != "savingstrackerv2_testdev":
        raise ValueError(f"Refusing to clean unexpected destination root: {repo_path}")

    if not os.path.exists(repo_path):
        if dry_run:
            print(f"[DRY RUN] Destination repository does not exist yet: {repo_path}")
        else:
            os.makedirs(repo_path, exist_ok=True)
            print(f"[CLEAN] Created destination repository: {repo_path}")
        return

    removed_files = 0
    removed_dirs = 0
    for entry_name in os.listdir(repo_path):
        target = os.path.join(repo_path, entry_name)
        is_directory = os.path.isdir(target) and not os.path.islink(target)

        if dry_run:
            if is_directory:
                removed_dirs += 1
            else:
                removed_files += 1
            continue

        try:
            if is_directory:
                shutil.rmtree(target)
                removed_dirs += 1
            else:
                os.remove(target)
                removed_files += 1
        except Exception as exc:
            raise RuntimeError(f"Failed to remove {target}: {exc}") from exc

    action = "[DRY RUN] Would remove" if dry_run else "[CLEAN] Removed"
    print(f"{action} {removed_files} files and {removed_dirs} folders from {repo_path}")


def migrate_files(dry_run=False, update_db_only=False, clean_new_repo=True):
    """Perform migration or metadata-only refresh for file_tracking records."""
    with app.app_context():
        from app.models import FileTracking
        from app import db

        session = db.session
        records = session.query(FileTracking).filter(FileTracking.is_deleted == False).all()

        if update_db_only:
            print("[MODE] Database refresh only")
        else:
            if clean_new_repo:
                print("[MODE] Clean destination repository and reload everything from OLD_REPO")
                clean_new_repository(NEW_REPO, dry_run=dry_run)
            else:
                print("[MODE] Copy, refolder, and update database without cleaning destination first")

        if dry_run:
            print(f"Found {len(records)} file_tracking records:")
            for rec in records:
                print(f"ID: {rec.id}, Initiative: {rec.initiative_id}, Name: {rec.file_name}, Path: {rec.file_path}, Size: {rec.file_size}, Type: {rec.file_type}")
            return

        search_roots = [NEW_REPO] if update_db_only else [OLD_REPO]
        file_index = build_file_index(search_roots)

        found_count = 0
        copied_count = 0
        updated_count = 0
        existing_count = 0
        missing_count = 0

        try:
            for rec in records:
                try:
                    initiative_id = rec.initiative_id
                    dest_path = get_destination_path(initiative_id, rec.file_name)
                    dest_folder = os.path.dirname(dest_path)
                    os.makedirs(dest_folder, exist_ok=True)

                    src_path = None
                    stored_path = dest_path

                    if os.path.isfile(dest_path):
                        src_path = dest_path
                        existing_count += 1
                        print(f"[NEW REPO] Found existing migrated file for {rec.file_name}: {src_path}")
                    elif rec.file_path and os.path.isfile(rec.file_path):
                        src_path = os.path.normpath(rec.file_path)
                        stored_path = src_path if update_db_only else dest_path
                        print(f"[DB path] Found for {rec.file_name}: {src_path}")
                    else:
                        print(f"[SEARCH] Looking for {rec.file_name} in repository index...")
                        src_path = find_file(
                            rec.file_name,
                            search_roots,
                            initiative_id=initiative_id,
                            file_index=file_index,
                        )
                        if src_path:
                            src_path = os.path.normpath(src_path)
                            if update_db_only:
                                stored_path = src_path
                            print(f"[SEARCH] Found {rec.file_name} at {src_path}")

                    if not src_path:
                        print(f"[MISSING] File not found: {rec.file_name} (initiative {initiative_id})")
                        missing_count += 1
                        continue
                    found_count += 1

                    normalized_src = os.path.normcase(os.path.normpath(src_path))
                    normalized_dest = os.path.normcase(dest_path)

                    if not update_db_only and normalized_src != normalized_dest:
                        try:
                            shutil.copy2(src_path, dest_path)
                            src_path = dest_path
                            stored_path = dest_path
                            copied_count += 1
                            print(f"[COPIED] {rec.file_name} to {dest_path}")
                        except Exception as e:
                            print(f"[ERROR] Failed to copy {src_path} -> {dest_path}: {e}")
                            continue
                    else:
                        print(f"[SKIP COPY] Using existing file for {rec.file_name}: {src_path}")

                    try:
                        update_file_tracking_record(rec, src_path, session, stored_path=stored_path)
                        session.commit()
                        updated_count += 1
                    except Exception as e:
                        session.rollback()
                        print(f"[ERROR] Failed to update file_tracking for {rec.file_name}: {e}")
                        continue

                    print(
                        f"[UPDATED] file_tracking id={rec.id}, "
                        f"path={rec.file_path}, size={rec.file_size}, type={rec.file_type}"
                    )
                except Exception as e:
                    session.rollback()
                    print(f"[ERROR] Unexpected failure for file_tracking id={getattr(rec, 'id', 'unknown')}: {e}")
                    continue
        except KeyboardInterrupt:
            print("Interrupted by user — committing progress so far...")
            session.commit()
            print(
                f"SUMMARY: Found: {found_count}, Copied: {copied_count}, "
                f"Updated: {updated_count}, Existing: {existing_count}, Missing: {missing_count}"
            )
            return

        session.commit()
        print(
            f"Migration complete. SUMMARY: Found: {found_count}, Copied: {copied_count}, "
            f"Updated: {updated_count}, Existing: {existing_count}, Missing: {missing_count}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate or refresh file_tracking file metadata (testdev).")
    parser.add_argument('--dry-run', action='store_true', help='Preview the cleanup/copy/update actions without modifying files or the database.')
    parser.add_argument(
        '--update-db-only',
        action='store_true',
        help='Only refresh file_path, file_size, and file_type from files already present in the new repository or current DB path.'
    )
    parser.add_argument(
        '--skip-clean',
        action='store_true',
        help='Do not delete the current contents of the new repository before reloading files from the old repository.'
    )
    args = parser.parse_args()
    migrate_files(
        dry_run=args.dry_run,
        update_db_only=args.update_db_only,
        clean_new_repo=not args.skip_clean,
    )
