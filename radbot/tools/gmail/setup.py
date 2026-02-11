"""Gmail account setup - run with: python -m radbot.tools.gmail.setup

Supports multiple accounts via --account flag:
    python -m radbot.tools.gmail.setup --account personal
    python -m radbot.tools.gmail.setup --account work

For remote/headless machines, use --port to set a fixed port and SSH tunnel:
    ssh -L 8085:localhost:8085 user@remote
    python -m radbot.tools.gmail.setup --account work --port 8085
"""

import argparse

from radbot.tools.gmail.gmail_auth import discover_accounts, run_setup

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Set up Gmail authentication for radbot"
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Account label (e.g. 'personal', 'work'). Creates a named token file.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Fixed port for OAuth callback (default: auto). Use with SSH tunnel for remote machines.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_accounts",
        help="List all configured Gmail accounts and exit.",
    )
    args = parser.parse_args()

    if args.list_accounts:
        accounts = discover_accounts()
        if not accounts:
            print("No Gmail accounts configured.")
            print("Run: python -m radbot.tools.gmail.setup --account <label>")
        else:
            print("Configured Gmail accounts:")
            for a in accounts:
                print(f"  {a['account']:15s} {a['email']}")
        raise SystemExit(0)

    label = args.account or "default"
    print(f"=== Gmail Account Setup ({label}) ===")
    if args.port:
        print(f"Listening on port {args.port} for OAuth callback.")
        print(
            f"If remote, tunnel with: ssh -L {args.port}:localhost:{args.port} user@this-machine"
        )
    print("Sign in with the Gmail account you want radbot to use.\n")

    success = run_setup(port=args.port, account=args.account)
    if success:
        print("\nSetup complete! Restart radbot to use the new account.")
    else:
        print("\nSetup failed.")
        raise SystemExit(1)
