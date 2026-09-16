import argparse
import sys

from .core import extractor_from_env


def main() -> None:
    parser = argparse.ArgumentParser(description="从受支持的公开网页提取 MP3")
    parser.add_argument("url", help="公开网页或视频链接")
    args = parser.parse_args()
    try:
        print(extractor_from_env().extract(args.url))
    except Exception as exc:
        print(f"提取失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
