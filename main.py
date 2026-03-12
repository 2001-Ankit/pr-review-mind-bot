"""ReviewMindBot - Main entry point."""

import sys
from app.cli import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
