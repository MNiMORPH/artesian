"""
Command line for artesian.

Two subcommands::

    artesian check numpy scipy mymodel      # can this run in the browser?
    artesian build app.py -o out -p . -r numpy scipy   # compile it

``build --serve`` compiles and then serves the result over HTTP, which is the
way to look at a demo locally: opening the page over ``file://`` trips the
browser's cross-origin rules for web workers.
"""

import argparse
import os
import sys

from ._version import __version__
from .build import DEFAULT_SELF_HOST, MODES, build_app
from .check import MISSING, check_requirements, format_report
from .payload import format_payload, payload


def _cmd_check(args):
    results = check_requirements(args.requirements, timeout=args.timeout)
    print(format_report(results))
    return 1 if any(v == MISSING for _, v, _ in results) else 0


def _cmd_build(args):
    html = build_app(
        args.app,
        args.outdir,
        packages=args.package,
        requirements=args.requirement,
        mode=args.mode,
        self_host=args.self_host,
        index=args.index,
        design_width=args.design_width,
        strip_wheels=args.strip_wheels,
        strip_vendored=args.strip_vendored,
    )
    print("built %s" % html)
    # Printed every time, not behind a flag. A reader's download was a surprise
    # precisely because nothing ever said what it was.
    print(format_payload(payload(args.outdir, args.app), args.outdir))
    if not args.serve:
        return 0

    import http.server
    import socketserver

    outdir = os.path.dirname(html)
    page = os.path.basename(html)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=outdir, **kw)

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("", args.port), Handler) as httpd:
        port = httpd.server_address[1]
        print("serving http://localhost:%d/%s  (Ctrl-C to stop)" % (port, page))
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="artesian",
        description="Compile a Python model into a self-contained WebAssembly "
                    "demo that runs in the browser with no server.")
    parser.add_argument("--version", action="version",
                        version="artesian %s" % __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    chk = sub.add_parser(
        "check", help="report whether requirements can install in the browser")
    chk.add_argument("requirements", nargs="+")
    chk.add_argument("--timeout", type=float, default=10.,
                     help="PyPI request timeout in seconds (default: 10)")
    chk.set_defaults(func=_cmd_check)

    bld = sub.add_parser("build", help="compile a Panel app to WebAssembly")
    bld.add_argument("app", help="Panel application .py file")
    bld.add_argument("-o", "--outdir", default="_artesian_build",
                     help="output directory (default: _artesian_build)")
    bld.add_argument("-p", "--package", action="append", default=[],
                     metavar="PATH",
                     help="local source tree to wheel and ship; repeatable")
    bld.add_argument("-r", "--requirement", action="append", default=[],
                     metavar="REQ",
                     help="extra requirement resolved in the browser; "
                          "repeatable")
    bld.add_argument("--mode", choices=MODES, default="pyodide-worker",
                     help="panel convert target (default: pyodide-worker)")
    bld.add_argument("--self-host", nargs="*", default=list(DEFAULT_SELF_HOST),
                     metavar="PKG",
                     help="packages to serve alongside the app rather than "
                          "from a CDN (default: %s)"
                          % " ".join(DEFAULT_SELF_HOST))
    bld.add_argument("--design-width", type=int, default=None,
                     help="width in CSS pixels the app is laid out for; the "
                          "embedding page scales the demo above it rather "
                          "than stretching it. Defaults to a DESIGN_WIDTH "
                          "declared in the app.")
    bld.add_argument("--strip-wheels", action="store_true",
                     help="drop source maps, TypeScript sources and test "
                          "suites from the self-hosted wheels (~9 MB off "
                          "panel); the wheels then differ from PyPI's and say "
                          "so in their own metadata")
    bld.add_argument("--strip-vendored", action="store_true",
                     help="also drop the JavaScript bundles the wheels vendor "
                          "(a further ~11 MB off panel). A compiled demo loads "
                          "its front end from a CDN, not from these; the build "
                          "fails if this app turns out to need them")
    bld.add_argument("--index", action="store_true",
                     help="also emit index.html (for several apps in one dir)")
    bld.add_argument("--serve", action="store_true",
                     help="serve the result over HTTP after building")
    bld.add_argument("--port", type=int, default=0,
                     help="port for --serve (default: an unused port)")
    bld.set_defaults(func=_cmd_build)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
