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
import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd()

if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent

SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from wizard.inventory import (
    build_inventory,
    duplicate_groups,
    inventory_summary,
    save_inventory,
)

# %%
CORPUS_DIR = Path(r"D:/baseia_v3/corpus/")
OUTPUT_DIR = PROJECT_ROOT / "data" / "inventory"

RECURSIVE = True
WORKERS = 10

# %%
inventory, errors = build_inventory(
    CORPUS_DIR,
    recursive=RECURSIVE,
    workers=WORKERS,
)

# %%
inventory.head()

# %%
inventory_summary(inventory)

# %%
inventory[
    [
        "filename",
        "size_mb",
        "page_count",
        "encrypted",
        "status",
    ]
].describe(include="all")

# %%
inventory["status"].value_counts(dropna=False)

# %%
inventory["page_count"].describe(percentiles=[0.25, 0.50, 0.75, 0.90, 0.95, 0.99])

# %%
inventory["size_mb"].describe(percentiles=[0.25, 0.50, 0.75, 0.90, 0.95, 0.99])

# %%
duplicates = duplicate_groups(inventory)
duplicates

# %%
errors

# %%
largest_documents = inventory.sort_values(
    "size_bytes",
    ascending=False,
).head(30)

largest_documents[["filename", "size_mb", "page_count", "relative_path"]]

# %%
longest_documents = inventory.sort_values(
    "page_count",
    ascending=False,
).head(30)

longest_documents[["filename", "page_count", "size_mb", "relative_path"]]

# %%
saved_paths = save_inventory(
    inventory,
    errors,
    OUTPUT_DIR,
)

saved_paths

# %%
