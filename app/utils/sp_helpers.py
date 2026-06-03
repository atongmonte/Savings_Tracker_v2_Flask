"""
Stored procedure helper utilities.
"""
from flask import current_app
from app import db


def run_distribution_procedure():
    """Execute dbo.SAVINGS_TRACKER_DAILY_DISTRIBUTION_PROCEDURE to completion.

    Uses a dedicated raw connection separate from the SQLAlchemy session so
    that the cursor-based stored procedure runs fully.  All intermediate
    result sets are drained via nextset() to prevent the driver from cutting
    the SP short before its internal cursor finishes iterating.
    """
    raw_conn = db.engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.execute("EXEC dbo.SAVINGS_TRACKER_DAILY_DISTRIBUTION_PROCEDURE")
        # Drain every result set so the SP's internal cursor runs to completion
        while cursor.nextset():
            pass
        raw_conn.commit()
    except Exception as e:
        current_app.logger.error(
            "SAVINGS_TRACKER_DAILY_DISTRIBUTION_PROCEDURE failed: %s", e
        )
    finally:
        raw_conn.close()
