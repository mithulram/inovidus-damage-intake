"""Local CLI for processing a body, an inbound-email JSON, or a scenario YAML."""

import argparse
from pathlib import Path

from .context import Context
from .models import InboundEmail
from .pipeline import process
from .providers import get_provider
from .scenarios import load_scenario, main as scenarios_main, run_scenario


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Schadenmeldung lokal verarbeiten")
    commands = parser.add_subparsers(dest="command", required=True)
    process_parser = commands.add_parser("process", help="E-Mail-Datei verarbeiten")
    process_parser.add_argument("file", type=Path)
    process_parser.add_argument("--provider", default=None)
    scenarios_parser = commands.add_parser("scenarios", help="Szenarien prüfen")
    scenarios_parser.add_argument("--provider", default=None)
    args = parser.parse_args(argv)
    if args.command == "scenarios":
        scenarios_main(["--provider", args.provider] if args.provider else [])
        return
    try:
        provider = get_provider(args.provider)
        path = args.file
        if path.suffix.lower() in {".yaml", ".yml"}:
            case, _ = run_scenario(load_scenario(path), provider=provider)
        else:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".json":
                email = InboundEmail.model_validate_json(text)
            elif path.suffix.lower() == ".txt":
                email = InboundEmail(body=text)
            else:
                raise ValueError("Erlaubte Dateitypen: .txt, .json, .yaml, .yml")
            case = process(email, Context.build(provider=provider))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(case.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
