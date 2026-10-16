from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA_DIRS = (DATA, ROOT / "src" / "prior_auth" / "handlers" / "fixtures")
LABEL = "SYNTHETIC"


def test_data_directory_is_labeled():
    assert (DATA / "SYNTHETIC.md").read_text().startswith("SYNTHETIC DATA ONLY")


def test_every_data_file_carries_the_label():
    unlabeled = [
        p.relative_to(ROOT)
        for d in DATA_DIRS
        for p in d.rglob("*")
        if p.is_file() and LABEL not in p.read_text(errors="ignore")[:2000].upper()
    ]
    assert unlabeled == []
