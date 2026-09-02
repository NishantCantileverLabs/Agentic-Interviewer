"""Retention purge job — the SOLE sanctioned deleter of interview_events.

    python scripts/purge_retention.py [--dry-run]

For sessions whose ended_at + retention_days is in the past: deletes their
interview_events rows and any recording/brief objects in MinIO. Evaluations
and briefs rows are kept (they are the durable outcome; their evidence quotes
survive inside the rubric). Run nightly via cron/scheduler.
"""

import pathlib
import sys
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.config import get_settings  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv


def main() -> None:
    settings = get_settings()
    engine = sa.create_engine(settings.database_url.replace("@postgres:", "@localhost:"))
    now = datetime.now(UTC)

    with engine.begin() as conn:
        # sole sanctioned bypass: retention purge (worker/maintenance path)
        conn.execute(sa.text("SELECT set_config('app.bypass_rls', 'on', false)"))
        expired = conn.execute(
            sa.text(
                "SELECT id, candidate_label, ended_at, retention_days FROM sessions "
                "WHERE ended_at IS NOT NULL"
            )
        ).fetchall()
        to_purge = [
            row for row in expired
            if row.ended_at + timedelta(days=row.retention_days) < now
        ]
        print(f"{len(to_purge)} session(s) past retention")
        for row in to_purge:
            count = conn.execute(
                sa.text("SELECT count(*) FROM interview_events WHERE session_id = :sid"),
                {"sid": str(row.id)},
            ).scalar()
            print(f"  {row.id} ({row.candidate_label}): {count} events", end="")
            if DRY_RUN:
                print(" [dry-run — kept]")
                continue
            conn.execute(
                sa.text("DELETE FROM interview_events WHERE session_id = :sid"),
                {"sid": str(row.id)},
            )
            print(" [purged]")

    if not DRY_RUN:
        try:
            from minio import Minio

            client = Minio(
                settings.s3_endpoint.replace("http://", "").replace("https://", ""),
                access_key=settings.s3_access_key,
                secret_key=settings.s3_secret_key,
                secure=settings.s3_endpoint.startswith("https"),
            )
            for row in to_purge:
                for obj in client.list_objects("recordings", prefix=str(row.id), recursive=True):
                    client.remove_object("recordings", obj.object_name)
                    print(f"  removed recording {obj.object_name}")
        except Exception as exc:  # noqa: BLE001 - purge of DB rows already done
            print(f"recording cleanup skipped: {exc}")

    print("PURGE COMPLETE" + (" (dry run)" if DRY_RUN else ""))


if __name__ == "__main__":
    main()
