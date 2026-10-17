"""Fails if any real health payer's name appears anywhere in the repository.

All payers here are fictional (Larkspur Health Plan, Tidewell Mutual). The list
covers major US payers and Blue plans; matching is case-insensitive on word
boundaries. Program names (Medicare, Medicaid) are not payers and are allowed.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REAL_PAYERS = [
    "UnitedHealthcare", "United Healthcare", "UnitedHealth", "Optum", "Aetna", "Cigna", "Evernorth", "Humana",
    "Anthem", "Elevance", "Wellpoint", "Blue Cross", "Blue Shield", "BCBS", "Kaiser Permanente", "Kaiser",
    "Centene", "Ambetter", "WellCare", "Health Net", "Molina", "Highmark", "CareFirst", "Florida Blue",
    "Premera", "Regence", "Wellmark", "Excellus", "Horizon BCBSNJ", "Independence Blue Cross", "Oscar Health",
    "Bright Health", "Clover Health", "Devoted Health", "Alignment Health", "EmblemHealth", "Oxford Health",
    "Harvard Pilgrim", "Tufts Health", "Point32Health", "Medica", "HealthPartners", "Priority Health",
    "UPMC Health Plan", "Geisinger Health Plan", "CareSource", "Amerigroup", "Magellan", "Carelon",
    "Caremark", "Express Scripts", "Fidelis", "MVP Health", "Capital Blue", "Lifewise", "Ascension Personalized",
    "Sentara", "Optima Health", "AvMed", "Simply Healthcare", "Peach State", "Sunshine Health",
]
PATTERN = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(n) for n in REAL_PAYERS) + r")(?![A-Za-z])", re.IGNORECASE)
SKIP = {"tests/test_no_real_payers.py", "uv.lock"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [ROOT / f for f in out if f not in SKIP]


IMAGES = {".png", ".jpg", ".jpeg"}


def test_no_real_payer_names_anywhere():
    """Text files, read as text. Binary files are not searched as text: compressed bytes can spell
    a name by chance and could never show one that is drawn; images are read by OCR below."""
    hits = []
    for path in tracked_files():
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # binary
        except (IsADirectoryError, FileNotFoundError):
            continue
        for m in PATTERN.finditer(text):
            hits.append(f"{path.relative_to(ROOT)}: {m.group(0)}")
    assert hits == []


def test_no_real_payer_names_in_images():
    """The text drawn in every PNG and JPEG, read by OCR (macOS Vision)."""
    import pytest
    ocrmac = pytest.importorskip("ocrmac.ocrmac")
    hits = []
    for path in tracked_files():
        if path.suffix.lower() in IMAGES and path.exists():
            text = " ".join(t for t, _, _ in ocrmac.OCR(str(path)).recognize())
            hits += [f"{path.relative_to(ROOT)}: {m.group(0)}" for m in PATTERN.finditer(text)]
    assert hits == []


def test_the_scanner_catches_a_planted_name(tmp_path):
    assert PATTERN.search("Prior authorization policy for aetna members")
    assert PATTERN.search("BLUE CROSS of somewhere")
    assert not PATTERN.search("Larkspur Health Plan and Tidewell Mutual")
    assert not PATTERN.search("Medicare Advantage and Medicaid managed care")
