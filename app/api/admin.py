"""
Admin API endpoints – distribution procedure management.

The stored procedure [dbo].[SAVINGS_TRACKER_DAILY_DISTRIBUTION_PROCEDURE] is
executed inside an explicit SQL Server transaction that holds an exclusive
application-level lock (sp_getapplock).  This prevents two runs from
overlapping and ensures the SP only starts after any competing lock holders
have released their locks (SQL Server will queue the lock request rather than
returning immediately when @LockTimeout > 0).

Each run is persisted to the `system_event_logs` table so history survives
process restarts.  The in-memory registry is kept only for live log streaming
while a job is running.
"""

import threading
import uuid
from datetime import datetime

from flask import jsonify, g, current_app
from sqlalchemy import text

from app.api import admin_bp
from app.utils.decorators import login_required

# ---------------------------------------------------------------------------
# In-memory job registry – used only for live log streaming.
# Keyed by job_id (str).  The most recent 50 jobs are retained so the page
# can stream log lines while the background thread is still running.
# History queries use the DB (SystemEventLog), not this dict.
# ---------------------------------------------------------------------------
_MAX_HISTORY = 50
_jobs: dict = {}
_jobs_lock = threading.Lock()


def _is_admin(user) -> bool:
    """Return True when *user* has administrator privileges."""
    if not user:
        return False
    return bool(
        user.has_permission("manage_users")
        or getattr(getattr(user, "role", None), "name", "") == "Admin"
    )


def _log(job_id: str, message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["logs"].append({"time": ts, "message": message})


def _set_status(job_id: str, status: str) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = status


def _run_distribution_job(job_id: str, db_row_id: int, app) -> None:
    """
    Background thread: acquire an exclusive application lock then execute the
    stored procedure.  The lock is automatically released when the transaction
    commits or rolls back.

    sp_getapplock return codes:
        0  = granted synchronously
        1  = granted after waiting
       -1  = timed out
       -2  = cancelled
       -3  = deadlock victim
       -999 = other error
    """
    with app.app_context():
        from app import db
        from app.models.system_event_log import SystemEventLog

        final_status = "failed"
        started_proc: datetime | None = None

        try:
            _log(job_id, "Waiting to acquire exclusive application lock …")
            _set_status(job_id, "waiting")
            _db_update_status(db, db_row_id, "waiting")

            with db.engine.connect() as conn:
                with conn.begin():
                    lock_sql = text("""
                        DECLARE @rc INT;
                        EXEC @rc = sp_getapplock
                            @Resource    = N'SAVINGS_TRACKER_DISTRIBUTION',
                            @LockMode    = N'Exclusive',
                            @LockOwner   = N'Transaction',
                            @LockTimeout = 600000;
                        SELECT @rc AS lock_result;
                    """)
                    row = conn.execute(lock_sql).fetchone()
                    lock_code = int(row[0]) if row is not None else -999

                    if lock_code < 0:
                        msg = (
                            f"Could not acquire lock (sp_getapplock returned {lock_code}). "
                            "Another process may still be running or the wait limit was reached."
                        )
                        _log(job_id, msg)
                        _set_status(job_id, "failed")
                        final_status = "failed"
                        return

                    if lock_code == 0:
                        _log(job_id, "Lock acquired immediately.")
                    else:
                        _log(job_id, f"Lock acquired after waiting (code {lock_code}).")

                    _log(job_id, "Executing [dbo].[SAVINGS_TRACKER_DAILY_DISTRIBUTION_PROCEDURE] …")
                    _set_status(job_id, "running")
                    _db_update_status(db, db_row_id, "running")
                    started_proc = datetime.now()

                    conn.execute(text("EXEC [dbo].[SAVINGS_TRACKER_DAILY_DISTRIBUTION_PROCEDURE]"))

                    elapsed = (datetime.now() - started_proc).total_seconds()
                    _log(job_id, f"Stored procedure completed successfully in {elapsed:.1f} second(s).")
                    _set_status(job_id, "success")
                    final_status = "success"
                    # Transaction commits here → lock is released automatically.

        except Exception as exc:
            _log(job_id, f"Error: {exc}")
            _set_status(job_id, "failed")
            final_status = "failed"
        finally:
            ended_at = datetime.now()
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["ended_at"] = ended_at.isoformat()
            _persist_final(db, db_row_id, job_id, final_status, ended_at, started_proc)
            _trim_job_history()


def _db_update_status(db, db_row_id: int, status: str) -> None:
    """Update only the status column of the DB row (non-blocking best-effort)."""
    try:
        from app.models.system_event_log import SystemEventLog
        row = db.session.get(SystemEventLog, db_row_id)
        if row:
            row.status = status
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def _persist_final(
    db,
    db_row_id: int,
    job_id: str,
    status: str,
    ended_at: datetime,
    started_proc: datetime | None,
) -> None:
    """Write the final status, full log text, and timing to the DB row."""
    try:
        from app.models.system_event_log import SystemEventLog
        row = db.session.get(SystemEventLog, db_row_id)
        if not row:
            return
        with _jobs_lock:
            job = _jobs.get(job_id, {})
            log_lines = job.get("logs", [])
        row.status  = status
        row.ended_at = ended_at
        row.log_text = "\n".join(
            f"[{entry['time']}] {entry['message']}" for entry in log_lines
        )
        if started_proc:
            row.duration_seconds = (ended_at - started_proc).total_seconds()
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def _trim_job_history() -> None:
    """Keep only the most recent _MAX_HISTORY entries to avoid unbounded growth."""
    with _jobs_lock:
        if len(_jobs) > _MAX_HISTORY:
            sorted_ids = sorted(_jobs.keys(), key=lambda k: _jobs[k]["started_at"])
            for old_id in sorted_ids[: len(_jobs) - _MAX_HISTORY]:
                del _jobs[old_id]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@admin_bp.route("/distribution/run", methods=["POST"])
@login_required
def run_distribution():
    """
    Start the daily distribution stored procedure in a background thread.
    Returns 409 if a job is already waiting or running.
    Returns 202 with the job_id on success.
    """
    user = g.current_user
    if not _is_admin(user):
        return jsonify({"error": "Admin access required."}), 403

    # Prevent duplicate concurrent runs
    with _jobs_lock:
        for job in _jobs.values():
            if job["status"] in ("waiting", "running", "starting"):
                return jsonify(
                    {
                        "error": "A distribution job is already in progress. "
                        "Please wait for it to finish.",
                        "job_id": job["job_id"],
                    }
                ), 409

    from app import db
    from app.models.system_event_log import SystemEventLog
    from app.utils.timezone import now_eastern

    app = current_app._get_current_object()
    job_id = str(uuid.uuid4())
    started_by = user.full_name or user.username
    started_at = now_eastern()

    # Create the DB row immediately so it exists even if the thread fails early.
    db_row = SystemEventLog(
        event_type="DISTRIBUTION_PROC",
        status="starting",
        started_by=started_by,
        started_at=started_at,
    )
    db.session.add(db_row)
    db.session.commit()
    db_row_id = db_row.id

    with _jobs_lock:
        _jobs[job_id] = {
            "job_id":    job_id,
            "db_row_id": db_row_id,
            "status":    "starting",
            "started_at": started_at.isoformat(),
            "ended_at":  None,
            "started_by": started_by,
            "logs": [
                {
                    "time":    started_at.strftime("%H:%M:%S"),
                    "message": f"Job initiated by {started_by}.",
                }
            ],
        }

    thread = threading.Thread(
        target=_run_distribution_job, args=(job_id, db_row_id, app), daemon=True
    )
    thread.start()

    return jsonify({"job_id": job_id, "db_row_id": db_row_id, "status": "starting"}), 202


@admin_bp.route("/distribution/status/<job_id>", methods=["GET"])
@login_required
def distribution_status(job_id: str):
    """Return the current status and log lines for a given job."""
    if not _is_admin(g.current_user):
        return jsonify({"error": "Admin access required."}), 403

    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found."}), 404

    return jsonify(job), 200


@admin_bp.route("/distribution/jobs", methods=["GET"])
@login_required
def list_distribution_jobs():
    """
    Return the 20 most recent distribution jobs from the DB (newest first).
    For any job that is still in-memory (currently running), live status from
    the in-memory registry overrides the DB row.
    """
    if not _is_admin(g.current_user):
        return jsonify({"error": "Admin access required."}), 403

    from app.models.system_event_log import SystemEventLog

    rows = (
        SystemEventLog.query
        .filter_by(event_type="DISTRIBUTION_PROC")
        .order_by(SystemEventLog.started_at.desc())
        .limit(20)
        .all()
    )

    # Build a quick lookup of live in-memory jobs by db_row_id
    with _jobs_lock:
        live_by_db_id = {
            j["db_row_id"]: j
            for j in _jobs.values()
            if "db_row_id" in j
        }

    results = []
    for row in rows:
        data = row.to_dict()
        live = live_by_db_id.get(row.id)
        if live and live["status"] in ("starting", "waiting", "running"):
            # Return live status for jobs still in progress
            data["status"]     = live["status"]
            data["job_id"]     = live["job_id"]
        results.append(data)

    return jsonify(results), 200
