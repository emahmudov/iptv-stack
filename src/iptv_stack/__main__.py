from __future__ import annotations

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
import json
import os

from .pipeline import build_dataset
from .portal import build_portal


def build_command(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = (root / args.output).resolve()
    summary = build_dataset(
        sources_path=(root / args.sources).resolve(),
        profile_path=(root / args.profile).resolve(),
        overrides_path=(root / args.overrides).resolve(),
        output_dir=output_dir,
    )

    channels_json = output_dir / "channels.json"
    portal_html = output_dir / "portal" / "index.html"
    build_portal(channels_json_path=channels_json, output_html_path=portal_html, title=args.title)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Portal: {portal_html}")


def serve_command(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = (root / args.output).resolve()
    os.chdir(output_dir)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), SimpleHTTPRequestHandler)
    print(f"Serving {output_dir} at http://127.0.0.1:{args.port}")
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto IPTV playlist builder")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Fetch, classify and generate playlists + portal")
    build.add_argument("--root", default=".", help="Project root")
    build.add_argument("--sources", default="config/sources.json", help="Path to sources json")
    build.add_argument("--profile", default="config/profile.json", help="Path to profile json")
    build.add_argument("--overrides", default="config/overrides.json", help="Path to overrides json")
    build.add_argument("--output", default="dist", help="Output directory")
    build.add_argument("--title", default="My IPTV Portal", help="Portal title")
    build.set_defaults(func=build_command)

    serve = sub.add_parser("serve", help="Serve dist folder as static site")
    serve.add_argument("--root", default=".", help="Project root")
    serve.add_argument("--output", default="dist", help="Output directory")
    serve.add_argument("--port", type=int, default=8080, help="HTTP port")
    serve.set_defaults(func=serve_command)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
