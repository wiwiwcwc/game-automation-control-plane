from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("success", "failure", "sleep", "unicode"), default="success")
    parser.add_argument("--seconds", type=float, default=0.2)
    args = parser.parse_args()
    print("fixture stdout", flush=True)
    print("fixture stderr", file=sys.stderr, flush=True)
    if args.mode == "sleep":
        time.sleep(args.seconds)
    if args.mode == "unicode":
        print("中文路径与输出", flush=True)
    if args.mode == "failure":
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
