# Wizard Inventory

## Estrutura

```text
src/
└── wizard/
    ├── __init__.py
    └── inventory.py

notebooks/
└── 00_inventory.py
```

## Instalação

```powershell
python -m pip install -r requirements-inventory.txt
```

## Uso

Abra `notebooks/00_inventory.py` como notebook Jupytext e ajuste:

```python
CORPUS_DIR = Path(r"D:\seu\corpus")
RECURSIVE = False
WORKERS = 8
```

Saída:

```text
data/inventory/
├── inventory.parquet
├── inventory.csv
├── inventory_errors.csv
├── inventory_duplicates.csv
└── inventory_summary.json
```
