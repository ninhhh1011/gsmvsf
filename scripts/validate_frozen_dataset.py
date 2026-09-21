"""Execute the canonical validator while redirecting its reports out of frozen data."""
import builtins
import io
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset_v1"
OUTPUT = ROOT / "runtime/migration/validation"

def main():
    original_open, original_io_open = builtins.open, io.open
    def redirected(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, bytes, Path)) and any(c in mode for c in "wax+"):
            path = Path(file).resolve()
            if path.is_relative_to(DATASET):
                file = OUTPUT / path.relative_to(DATASET)
                file.parent.mkdir(parents=True, exist_ok=True)
        return original_open(file, mode, *args, **kwargs)
    try:
        builtins.open = io.open = redirected
        runpy.run_path(str(DATASET / "validation/validate_dataset.py"), run_name="__main__")
    finally:
        builtins.open, io.open = original_open, original_io_open

if __name__ == "__main__":
    main()
