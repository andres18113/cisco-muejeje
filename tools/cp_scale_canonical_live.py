"""Compatible CP-SCALE LIVE entry point; composition lives in the CLI adapter."""
from __future__ import annotations

from packet_tracer_mcp.adapters.cli.cp_scale_live import (
    main,
    run,
)


if __name__ == "__main__":
    raise SystemExit(main())
