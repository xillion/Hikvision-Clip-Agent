"""M0 process entrypoint.

M0 intentionally contains no network, FFmpeg, or worker behavior.
"""


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
