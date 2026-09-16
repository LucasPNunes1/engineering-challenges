"""The 15 filings explicitly in scope for the Bilan challenge."""

from pathlib import Path


TARGETS: tuple[tuple[str, str], ...] = (
    ("820561470", "bilan_2023-06-05_6493e4372f502414800f8164.pdf"),
    ("820561470", "bilan_2023-06-13_6543d3fd08093cdace058668.pdf"),
    ("820561470", "bilan_2024-01-15_67458f18cea78a70070fa226.pdf"),
    ("328024377", "bilan_2020-12-24_63e8ebbb54febda17c19ee7c.pdf"),
    ("328024377", "bilan_2021-12-17_63e8ebbb54febda17c19ee7d.pdf"),
    ("328024377", "bilan_2022-12-13_63e8ebbb54febda17c19ee7e.pdf"),
    ("445070311", "bilan_2022-02-14_63e2481c916269756a09542b.pdf"),
    ("445070311", "bilan_2023-11-21_65a4095d5fd178b16b09b860.pdf"),
    ("445070311", "bilan_2025-05-15_6860f28ca0138eae340c7453.pdf"),
    ("504304205", "bilan_2017-05-31_63e13943526e1f30cd100db5.pdf"),
    ("504304205", "bilan_2018-10-24_63e13943526e1f30cd100db6.pdf"),
    ("504304205", "bilan_2024-08-06_66cd893cedec9b09d50191e8.pdf"),
    ("401009741", "bilan_2022-11-30_63e881158be6eb9f9d1ff975.pdf"),
    ("401009741", "bilan_2023-11-20_65784e5da67d84faf4042736.pdf"),
    ("401009741", "bilan_2025-10-03_68f0a715f28d8aaf48046416.pdf"),
)


def document_id(pdf_name: str) -> str:
    return Path(pdf_name).stem.rsplit("_", maxsplit=1)[1]
