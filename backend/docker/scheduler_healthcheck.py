"""Docker healthcheck for the dedicated `scheduler` container.

The scheduler serves no HTTP port, so the image's default HEALTHCHECK (which probes
:8000) does not apply. Instead this checks the scheduler heartbeat recorded by
backend/app/services/scheduler.py (``get_scheduler_heartbeat(db)``):

  exit 0  heartbeat fresh, or this build has no heartbeat support yet (graceful)
  exit 1  heartbeat stale/missing, or the database lookup failed

Run as:  python /app/backend/docker/scheduler_healthcheck.py
"""
import sys
from pathlib import Path

# Run by path, so make the repo root (/app in the image) importable as `backend.*`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    try:
        from backend.app.api.v1.endpoints.health import scheduler_heartbeat_status
    except Exception as exc:  # pragma: no cover - image without the helper
        print(f"scheduler healthcheck: helper unavailable ({exc}); assuming healthy")
        return 0

    result = scheduler_heartbeat_status()
    state = result.get("status")
    print(f"scheduler healthcheck: {result}")
    if state in ("ok", "unavailable"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
