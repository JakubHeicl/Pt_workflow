from pathlib import Path
import argparse

from .engine import run, show_status, restore, stop_loop
from .interaction import NoInteraction, ConsoleInteraction, Logger

parser = argparse.ArgumentParser()
parser.add_argument("--status", action="store_true", help="Show status of all cases in the repository.")
parser.add_argument("--restore", action="store_true", help="Restore the workflow from the repository and cancel all running jobs. Use with caution as this will remove the repository and all run folders.")
parser.add_argument("--do-not-ask", action="store_true", help="Do not ask for confirmation when starting new jobs or when restoring the workflow. Use with caution as this may lead to unintended consequences.")
parser.add_argument("--log-file", type=Path, default=None, help="Path to the log file.")
parser.add_argument("--loop", action="store_true", help="Run the workflow in a loop, checking for new cases and running jobs every few seconds.")
parser.add_argument("--stop-loop", action="store_true", help="Stop the workflow loop by creating a STOP_FILE in the repository folder. The workflow will check for this file at the end of each loop and stop if it exists.")

if __name__ == "__main__":
    args = parser.parse_args()
    logger = Logger(args.log_file)

    if args.do_not_ask:
        interaction = NoInteraction(logger)
    else:
        interaction = ConsoleInteraction(logger)

    if args.status:
        show_status(logger)
    elif args.restore:
        restore(logger, interaction)
    elif args.stop_loop:
        stop_loop()
    else:
        run(logger, interaction, loop=args.loop)