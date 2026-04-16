import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_SPEC_JSON = "TC1263_specs.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Digi-Key search and ranking scripts in sequence."
    )
    parser.add_argument(
        "spec_json",
        nargs="?",
        default=DEFAULT_SPEC_JSON,
        help="Input spec JSON path (absolute or relative to this script directory).",
    )
    return parser.parse_args()


def resolve_spec_path(spec_json, base_dir):
    spec_path = Path(spec_json)
    if not spec_path.is_absolute():
        spec_path = base_dir / spec_path
    return spec_path.resolve()


def run_script(script_path, base_dir, spec_path):
    print(f"\n=== Running {script_path.name} ===")
    subprocess.run(
        [sys.executable, str(script_path), "--spec", str(spec_path)],
        cwd=str(base_dir),
        check=True,
    )


def main():
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    spec_path = resolve_spec_path(args.spec_json, base_dir)
    scripts = [base_dir / "search.py", base_dir / "rank2.py"]

    if not spec_path.exists():
        print(f"Missing input spec JSON: {spec_path}")
        return 1

    print(f"Using input spec: {spec_path}")

    for script in scripts:
        if not script.exists():
            print(f"Missing required script: {script.name}")
            return 1

    try:
        for script in scripts:
            run_script(script, base_dir, spec_path)
    except subprocess.CalledProcessError as exc:
        failed_script = Path(exc.cmd[1]).name if len(exc.cmd) > 1 else "unknown"
        print(f"\nPipeline stopped: {failed_script} failed with exit code {exc.returncode}.")
        return exc.returncode or 1

    print("\nCompleted successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
