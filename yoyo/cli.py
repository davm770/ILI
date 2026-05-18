from __future__ import annotations

import json
import sys

from dotenv import load_dotenv

from .match import match


def main() -> None:
    load_dotenv()
    if len(sys.argv) < 2:
        print("usage: python -m yoyo <ig_username>")
        sys.exit(1)
    res = match(sys.argv[1])
    print(json.dumps(res.to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()
