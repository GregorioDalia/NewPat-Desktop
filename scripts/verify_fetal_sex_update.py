"""Check the installed fetal-sex workflow against both published cases."""

import argparse
from pathlib import Path
import sys
import tempfile

# Embedded Python excludes sibling verification modules from its default path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from acceptance.installed_models import (FETAL_SEX_EXAMPLES, check_fetal_sex,
                                        combined_fetal_dnp, copy_fetal_sex_fixtures, fetal_sex_inputs, tree_hashes)
from newpat.errors import NewPatError
from newpat.experiments.runner import DockerComposeRunner
from newpat.experiments.workflows import Workflows
from newpat.paths import ProjectLayout
from verify_contamination_update import check_bundled_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", help="optional prefix for the verification runs")
    args = parser.parse_args()
    layout = ProjectLayout.discover()
    try:
        if layout.project_dir != Path(__file__).resolve().parents[1]:
            raise ValueError("Choose the installed project that contains this verification script.")
        layout.ensure_storage_dirs()
        client = Workflows(layout, DockerComposeRunner(layout))
        with tempfile.TemporaryDirectory(prefix="fetal-sex-self-test-", dir=layout.data_dir) as directory:
            fixture = Path(directory) / "reference"
            combined_dir = Path(directory) / "combined"
            copy_fetal_sex_fixtures(layout.project_dir / "tests/fixtures/fetal_sex", fixture)
            cases = []
            for sample in FETAL_SEX_EXAMPLES:
                autosomes, x, y = fetal_sex_inputs(fixture, sample)
                combined = combined_fetal_dnp(autosomes, x, combined_dir)
                cases.append((sample, autosomes, x, y, combined))
            hashes = tree_hashes(Path(directory))
            for sample, autosomes, x, y, combined in cases:
                for label, inputs in (("split", {"autosomes": autosomes, "x": x}), ("combined", {"dnp": combined})):
                    run_name = f"{args.run_name}-{sample}-{label}" if args.run_name else None
                    run = client.fetal_sex(**inputs, y=y, run_name=run_name)
                    check_bundled_run(run, layout, workflow="fetal-sex")
                    result = check_fetal_sex(run, fixture, sample)
                    print(f"{sample} ({label}): {result['fetal_sex']} (four matching tables), {run}", flush=True)
            if tree_hashes(Path(directory)) != hashes:
                raise ValueError("Fetal-sex inputs or reference outputs changed during execution.")
    except (NewPatError, ValueError, OSError) as exc:
        print(f"Fetal-sex verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
