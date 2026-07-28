# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path.cwd()

if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent


INVENTORY_PATH = PROJECT_ROOT / "data" / "inventory" / "inventory.parquet"

SAMPLE_DIR = PROJECT_ROOT / "data" / "samples"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_SIZE = 120
RANDOM_STATE = 42
# %%
inventory = pd.read_parquet(INVENTORY_PATH)

print(f"Documentos no inventário: {len(inventory)}")
inventory.head()
# %%
eligible = inventory[
    inventory["status"].eq("ok")
    & inventory["sha256"].notna()
    & inventory["path"].notna()
].copy()

eligible = (
    eligible.sort_values("relative_path")
    .drop_duplicates(
        subset="sha256",
        keep="first",
    )
    .reset_index(drop=True)
)

eligible["page_count"] = pd.to_numeric(
    eligible["page_count"],
    errors="coerce",
)

eligible["size_mb"] = pd.to_numeric(
    eligible["size_mb"],
    errors="coerce",
)

print(f"Documentos elegíveis e únicos: {len(eligible)}")
# %%
eligible["page_bucket"] = pd.cut(
    eligible["page_count"],
    bins=[
        -np.inf,
        2,
        5,
        10,
        25,
        50,
        100,
        250,
        np.inf,
    ],
    labels=[
        "001_002",
        "003_005",
        "006_010",
        "011_025",
        "026_050",
        "051_100",
        "101_250",
        "251_plus",
    ],
)

eligible["size_bucket"] = pd.cut(
    eligible["size_mb"],
    bins=[
        -np.inf,
        0.25,
        1,
        5,
        20,
        100,
        np.inf,
    ],
    labels=[
        "000_025mb",
        "025_001mb",
        "001_005mb",
        "005_020mb",
        "020_100mb",
        "100mb_plus",
    ],
)

eligible["encrypted_bucket"] = (
    eligible["encrypted"]
    .fillna(False)
    .map(
        {
            False: "not_encrypted",
            True: "encrypted",
        }
    )
)

eligible["stratum"] = (
    eligible["page_bucket"].astype(str)
    + "|"
    + eligible["size_bucket"].astype(str)
    + "|"
    + eligible["encrypted_bucket"]
)
# %%
strata = (
    eligible.groupby("stratum", observed=True)
    .size()
    .rename("population")
    .sort_values(ascending=False)
    .reset_index()
)

strata


# %%
def stratified_sample(
    dataframe: pd.DataFrame,
    *,
    sample_size: int,
    random_state: int,
) -> pd.DataFrame:
    if sample_size >= len(dataframe):
        return dataframe.copy()

    groups = list(
        dataframe.groupby(
            "stratum",
            observed=True,
            sort=True,
        )
    )

    minimum_per_stratum = 1

    selected_parts = []

    for _, group in groups:
        selected_parts.append(
            group.sample(
                n=min(minimum_per_stratum, len(group)),
                random_state=random_state,
            )
        )

    selected = pd.concat(
        selected_parts,
        ignore_index=False,
    ).drop_duplicates("sha256")

    remaining_slots = sample_size - len(selected)

    if remaining_slots <= 0:
        return selected.sample(
            n=sample_size,
            random_state=random_state,
        ).reset_index(drop=True)

    remaining = dataframe[~dataframe["sha256"].isin(selected["sha256"])].copy()

    population_weights = (
        remaining.groupby("stratum", observed=True).size().div(len(remaining))
    )

    additional_parts = []

    for stratum, group in remaining.groupby(
        "stratum",
        observed=True,
        sort=True,
    ):
        target = round(population_weights.loc[stratum] * remaining_slots)

        target = min(
            max(target, 0),
            len(group),
        )

        if target:
            additional_parts.append(
                group.sample(
                    n=target,
                    random_state=random_state,
                )
            )

    if additional_parts:
        selected = pd.concat(
            [selected, *additional_parts],
            ignore_index=False,
        ).drop_duplicates("sha256")

    missing = sample_size - len(selected)

    if missing > 0:
        remaining = dataframe[~dataframe["sha256"].isin(selected["sha256"])]

        selected = pd.concat(
            [
                selected,
                remaining.sample(
                    n=min(missing, len(remaining)),
                    random_state=random_state,
                ),
            ],
            ignore_index=False,
        )

    if len(selected) > sample_size:
        selected = selected.sample(
            n=sample_size,
            random_state=random_state,
        )

    return selected.sort_values(
        [
            "page_bucket",
            "size_bucket",
            "relative_path",
        ]
    ).reset_index(drop=True)


# %%
sample = stratified_sample(
    eligible,
    sample_size=SAMPLE_SIZE,
    random_state=RANDOM_STATE,
)

print(f"Documentos na amostra: {len(sample)}")
sample.head()

# %%
edge_parts = [
    eligible.nlargest(10, "size_mb"),
    eligible.nlargest(10, "page_count"),
    eligible.nsmallest(10, "size_mb"),
    eligible[
        eligible["encrypted"].fillna(False)
    ].head(10),
]

edge_cases = (
    pd.concat(edge_parts, ignore_index=True)
    .drop_duplicates("sha256")
)

edge_cases = edge_cases[
    ~edge_cases["sha256"].isin(sample["sha256"])
].reset_index(drop=True)

print(f"Casos extremos adicionais: {len(edge_cases)}")

# %%
manifest_columns = [
    "document_id",
    "sha256",
    "path",
    "relative_path",
    "filename",
    "size_mb",
    "page_count",
    "encrypted",
    "page_bucket",
    "size_bucket",
    "stratum",
]

SAMPLE_MANIFEST = SAMPLE_DIR / "benchmark_sample.csv"
EDGE_CASES_MANIFEST = SAMPLE_DIR / "benchmark_edge_cases.csv"

sample[manifest_columns].to_csv(
    SAMPLE_MANIFEST,
    index=False,
    encoding="utf-8-sig",
)

edge_cases[manifest_columns].to_csv(
    EDGE_CASES_MANIFEST,
    index=False,
    encoding="utf-8-sig",
)

print(SAMPLE_MANIFEST.resolve())
print(EDGE_CASES_MANIFEST.resolve())

# %%
display(
    sample["page_bucket"].value_counts(
        sort=False,
        dropna=False,
    ),
    sample["size_bucket"].value_counts(
        sort=False,
        dropna=False,
    ),
    sample["stratum"].value_counts(),
)

# %%
