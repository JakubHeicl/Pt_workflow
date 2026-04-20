from pathlib import Path
import argparse

from .engine import run, show_status, restore, stop_loop, initialize
from .config import SUG_DIR
from .interaction import NoInteraction, ConsoleInteraction, Logger
from .smiles import process_smiles_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="Initialize the repository and create the necessary folders and files.")
    parser.add_argument("--status", action="store_true", help="Show status of all cases in the repository.")
    parser.add_argument("--restore", action="store_true", help="Restore the workflow from the repository and cancel all running jobs. Use with caution as this will remove the repository and all run folders.")
    parser.add_argument("--auto", action="store_true", help="Do not ask for confirmation when starting new jobs or when restoring the workflow. Use with caution as this may lead to unintended consequences.")
    parser.add_argument("--log-file", type=Path, default=None, help="Path to the log file.")
    parser.add_argument("--loop", action="store_true", help="Run the workflow in a loop, checking for new cases and running jobs every few seconds.")
    parser.add_argument("--stop", action="store_true", help="Stop the workflow loop by creating a STOP_FILE in the repository folder. The workflow will check for this file at the end of each loop and stop if it exists.")
    parser.add_argument("--suggest_from_smiles", type=Path, help="Path to a file containing SMILES strings for which to generate suggestions.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger = Logger(args.log_file)

    if args.auto:
        interaction = NoInteraction(logger)
    else:
        interaction = ConsoleInteraction(logger)

    if args.status:
        show_status(logger)
    elif args.init:
        initialize(logger)
    elif args.restore:
        restore(logger, interaction)
    elif args.stop:
        stop_loop()
    elif args.suggest_from_smiles:
        if not args.suggest_from_smiles.is_file():
            logger.log(f"File {args.suggest_from_smiles} does not exist.")
            return 1
        process_smiles_file(
            args.suggest_from_smiles,
            out_dir=SUG_DIR,
            charge=0,
            mult=1,
            route_line="#p",
        )
    else:
        run(logger, interaction, loop=args.loop)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
