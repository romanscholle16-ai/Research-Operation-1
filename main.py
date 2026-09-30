"""Strategy Research Lab entry point.

Phase 1: loads config, initializes logging/database/state, emits
start/stop events, and shuts down cleanly. No autonomous research loop yet.
"""

from app.core.app import main

if __name__ == "__main__":
    main()
