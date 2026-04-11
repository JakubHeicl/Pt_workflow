from .engine import run, show_status, restore
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--status", action="store_true", help="Show status of all cases in the repository.")
parser.add_argument("--restore", action="store_true", help="Restore the workflow from the repository and cancel all running jobs. Use with caution as this will remove the repository and all run folders.")

if __name__ == "__main__":
    args = parser.parse_args()
    if args.status:
        show_status()
    elif args.restore:
        restore()
    else:
        run()