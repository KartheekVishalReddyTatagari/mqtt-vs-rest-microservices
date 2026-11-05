"""Copy run results out of the Docker volume onto the host.

Services write to the named volume "mqtt-vs-rest-results" (fast Linux
storage inside the Docker VM). This copies one run folder out, e.g.

    python experiments/export_results.py rest/my-run-id
"""

import subprocess
import sys
from pathlib import Path

VOLUME = "mqtt-vs-rest-results"
REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "results" / "raw"
HELPER_IMAGE = "mqtt-vs-rest/rest:latest"   # already built; avoids pulling another image


def _clean(rel_path: str) -> str:
    return rel_path.strip("/").replace("\\", "/")


def export_to(rel_path: str, dest_dir: Path, docker: str = "docker") -> Path:
    """Copy <volume>/<rel_path>/ into dest_dir/ (created if needed)."""
    rel_path = _clean(rel_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [docker, "run", "--rm", "-v", f"{VOLUME}:/data:ro", "-v", f"{dest_dir.resolve()}:/out",
         HELPER_IMAGE, "sh", "-c", f'cp -a "/data/{rel_path}/." /out/'],
        check=True, capture_output=True,
    )
    return dest_dir


def export_run(rel_path: str, dest_root: Path = RAW, docker: str = "docker") -> Path:
    """Copy <volume>/<rel_path> to <dest_root>/<rel_path> and return the destination."""
    rel_path = _clean(rel_path)
    return export_to(rel_path, dest_root / rel_path, docker)


def delete_run(rel_path: str, docker: str = "docker") -> None:
    """Remove a run folder from the volume (after it has been exported)."""
    rel_path = _clean(rel_path)
    subprocess.run(
        [docker, "run", "--rm", "-v", f"{VOLUME}:/data", HELPER_IMAGE, "rm", "-rf", f"/data/{rel_path}"],
        check=True, capture_output=True,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python experiments/export_results.py <architecture>/<run_id>")
    print(export_run(sys.argv[1]))
