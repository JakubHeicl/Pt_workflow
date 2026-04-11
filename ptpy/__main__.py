from .engine import run, show_status
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--status", action="store_true", help="Show status of all cases in the repository.")

if __name__ == "__main__":
    args = parser.parse_args()
    if args.status:
        show_status()
    else:
        run()