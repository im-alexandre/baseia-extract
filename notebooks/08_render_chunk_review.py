from __future__ import annotations

import html
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path.cwd()
if PROJECT_ROOT.name == "notebooks":
    PROJECT_ROOT = PROJECT_ROOT.parent

CHUNKS_ROOT = PROJECT_ROOT / "artifacts" / "chunks_prototype"
CHUNKS_PATH = CHUNKS_ROOT / "chunks.jsonl"
REVIEW_DIR = CHUNKS_ROOT / "review"
HTML_PATH = REVIEW_DIR / "chunk_review.html"
SAMPLE_PATH = REVIEW_DIR / "review_sample.jsonl"

SAMPLE_SIZE = 30
RANDOM_SEED = 42
MAX_TEXT_PREVIEW_CHARS = 12000

REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSON inválido em {path}, linha {line_number}") from error
            if not isinstance(value, dict):
                raise TypeError(f"Linha {line_number} de {path} não contém um objeto.")
            rows.append(value)
    return rows


def stratified_sample(rows: list[dict[str, Any]], sample_size: int, seed: int) -> list[dict[str, Any]]:
    if len(rows) <= sample_size:
        return sorted(rows, key=lambda row: (str(row.get("source_name") or ""), int(row.get("ordinal") or 0)))

    rng = random.Random(seed)
    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = str(row.get("document_id") or row.get("source_name") or "")
        by_document[key].append(row)

    chosen = [rng.choice(document_rows) for document_rows in by_document.values()]
    chosen_ids = {item.get("id") for item in chosen}
    remaining = [row for row in rows if row.get("id") not in chosen_ids]

    extremes = sorted(remaining, key=lambda row: int(row.get("char_count") or 0))
    for candidate in extremes[:3] + extremes[-3:]:
        if len(chosen) >= sample_size:
            break
        if candidate.get("id") not in chosen_ids:
            chosen.append(candidate)
            chosen_ids.add(candidate.get("id"))

    remaining = [row for row in remaining if row.get("id") not in chosen_ids]
    rng.shuffle(remaining)
    chosen.extend(remaining[: max(0, sample_size - len(chosen))])

    return sorted(chosen[:sample_size], key=lambda row: (str(row.get("source_name") or ""), int(row.get("ordinal") or 0)))


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def badge(label: str, enabled: bool) -> str:
    css_class = "badge badge-on" if enabled else "badge"
    return f'<span class="{css_class}">{h(label)}</span>'


def render_chunk_card(chunk: dict[str, Any], index: int) -> str:
    section_path = " › ".join(chunk.get("section_path") or [])
    text = str(chunk.get("text") or "")
    if len(text) > MAX_TEXT_PREVIEW_CHARS:
        text = text[:MAX_TEXT_PREVIEW_CHARS] + "\n\n[… texto truncado na revisão …]"

    roles = ", ".join(f"{key}={value}" for key, value in sorted((chunk.get("role_counts") or {}).items()))
    block_ids = "\n".join(chunk.get("block_ids") or [])
    overlap_ids = "\n".join(chunk.get("overlap_block_ids") or [])
    asset_ids = "\n".join(chunk.get("asset_ids") or [])
    search_blob = " ".join([
        str(chunk.get("source_name") or ""),
        section_path,
        str(chunk.get("id") or ""),
        text,
    ]).lower()

    return f"""
    <article class="chunk-card" data-search="{h(search_blob)}">
      <header>
        <div>
          <div class="index">#{index:03d}</div>
          <h2>{h(chunk.get('source_name'))}</h2>
          <p class="section">{h(section_path or '(sem seção)')}</p>
        </div>
        <div class="metrics">
          <strong>{h(chunk.get('char_count'))}</strong> chars
          <strong>{h(chunk.get('token_count_estimate'))}</strong> tokens≈
          <strong>{len(chunk.get('block_ids') or [])}</strong> blocos
        </div>
      </header>
      <div class="badges">
        {badge('lista', bool(chunk.get('contains_list')))}
        {badge('equação', bool(chunk.get('contains_equation')))}
        {badge('tabela', bool(chunk.get('contains_table')))}
        {badge('figura', bool(chunk.get('contains_figure')))}
        {badge('overlap', bool(chunk.get('overlap_block_ids')))}
      </div>
      <dl class="metadata">
        <dt>Chunk</dt><dd><code>{h(chunk.get('id'))}</code></dd>
        <dt>Documento</dt><dd><code>{h(chunk.get('document_id'))}</code></dd>
        <dt>Seção</dt><dd><code>{h(chunk.get('section_id'))}</code></dd>
        <dt>Páginas</dt><dd>{h(chunk.get('page_start'))}–{h(chunk.get('page_end'))}</dd>
        <dt>Ordinal</dt><dd>{h(chunk.get('ordinal'))}</dd>
        <dt>Papéis</dt><dd>{h(roles)}</dd>
      </dl>
      <section class="text">
        <h3>Texto</h3>
        <pre>{h(text)}</pre>
      </section>
      <details>
        <summary>IDs de origem</summary>
        <div class="details-grid">
          <div><h4>Blocos</h4><pre>{h(block_ids)}</pre></div>
          <div><h4>Overlap</h4><pre>{h(overlap_ids or '(nenhum)')}</pre></div>
          <div><h4>Assets</h4><pre>{h(asset_ids or '(nenhum)')}</pre></div>
        </div>
      </details>
    </article>
    """


def main() -> None:
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"{CHUNKS_PATH} não existe. Execute 07_build_chunks.py primeiro.")

    chunks = load_jsonl(CHUNKS_PATH)
    if not chunks:
        raise RuntimeError("O arquivo consolidado de chunks está vazio.")

    sample = stratified_sample(chunks, SAMPLE_SIZE, RANDOM_SEED)
    with SAMPLE_PATH.open("w", encoding="utf-8") as file:
        for chunk in sample:
            file.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    char_counts = [int(chunk.get("char_count") or 0) for chunk in chunks]
    document_counts = Counter(str(chunk.get("source_name") or "") for chunk in chunks)
    cards = "\n".join(render_chunk_card(chunk, index) for index, chunk in enumerate(sample, start=1))
    document_options = "\n".join(
        f'<option value="{h(name.lower())}">{h(name)} ({count})</option>'
        for name, count in sorted(document_counts.items())
    )

    page = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BaseIA — revisão de chunks</title>
<style>
:root{{--bg:#f4f5f7;--panel:#fff;--text:#17191c;--muted:#667085;--border:#d8dde6;--accent:#3056d3;--success:#137333;--code:#f7f8fa}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111317;--panel:#191c22;--text:#edf0f5;--muted:#a5adba;--border:#343a46;--accent:#8aa4ff;--success:#69d184;--code:#12151a}}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif;line-height:1.5}}
.container{{width:min(1180px,calc(100% - 32px));margin:auto;padding:32px 0 80px}} .hero,.toolbar,.chunk-card{{background:var(--panel);border:1px solid var(--border);border-radius:14px}}
.hero{{padding:24px;margin-bottom:16px}} .hero h1{{margin:0 0 8px;font-size:28px}} .summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:20px}}
.summary div{{border:1px solid var(--border);border-radius:10px;padding:12px}} .summary strong{{display:block;font-size:22px}}
.toolbar{{position:sticky;top:12px;z-index:10;display:grid;grid-template-columns:1fr minmax(240px,360px);gap:12px;padding:12px;margin-bottom:18px;box-shadow:0 8px 30px #0002}}
input,select{{width:100%;border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:10px 12px;font:inherit}}
.chunk-card{{padding:22px;margin-bottom:18px}} .chunk-card header{{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}} h2,h3,h4{{margin-top:0}} h2{{margin-bottom:4px;font-size:20px}}
.index,.section,.metrics{{color:var(--muted)}} .metrics{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;white-space:nowrap}} .metrics strong{{color:var(--text);margin-left:8px}}
.badges{{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}} .badge{{border:1px solid var(--border);border-radius:999px;padding:3px 9px;color:var(--muted);font-size:12px}} .badge-on{{color:var(--success);border-color:currentColor;font-weight:700}}
.metadata{{display:grid;grid-template-columns:90px 1fr;gap:5px 12px;margin:0 0 20px;font-size:13px}} .metadata dt{{color:var(--muted)}} .metadata dd{{margin:0;min-width:0;overflow-wrap:anywhere}}
pre,code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}} .text pre{{background:var(--code);border:1px solid var(--border);border-radius:10px;padding:18px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.6}}
details{{margin-top:16px;border-top:1px solid var(--border);padding-top:14px}} summary{{cursor:pointer;color:var(--accent);font-weight:700}} .details-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}} .details-grid pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}}
.hidden{{display:none}} @media(max-width:760px){{.toolbar,.details-grid{{grid-template-columns:1fr}} .chunk-card header{{display:block}} .metrics{{justify-content:flex-start;margin-top:10px}}}}
</style>
</head>
<body>
<main class="container">
<section class="hero"><h1>Revisão estrutural de chunks</h1><p>Amostra estratificada para inspeção de cortes, contexto e rastreabilidade.</p>
<div class="summary"><div><strong>{len(chunks)}</strong> chunks totais</div><div><strong>{len(sample)}</strong> revisados</div><div><strong>{len(document_counts)}</strong> documentos</div><div><strong>{round(sum(char_counts)/len(char_counts),1)}</strong> chars médios</div><div><strong>{min(char_counts)}</strong> chars mínimos</div><div><strong>{max(char_counts)}</strong> chars máximos</div></div></section>
<section class="toolbar"><input id="search" type="search" placeholder="Buscar texto, documento, seção ou ID"><select id="document"><option value="">Todos os documentos</option>{document_options}</select></section>
<section id="cards">{cards}</section>
</main>
<script>
const search=document.querySelector('#search'); const documentFilter=document.querySelector('#document'); const cards=[...document.querySelectorAll('.chunk-card')];
function applyFilters(){{const query=search.value.trim().toLowerCase();const documentName=documentFilter.value.trim().toLowerCase();for(const card of cards){{const blob=card.dataset.search||'';card.classList.toggle('hidden',!((!query||blob.includes(query))&&(!documentName||blob.includes(documentName))))}}}}
search.addEventListener('input',applyFilters);documentFilter.addEventListener('change',applyFilters);
</script>
</body>
</html>"""

    HTML_PATH.write_text(page, encoding="utf-8")
    print(f"Chunks carregados: {len(chunks)}")
    print(f"Chunks na revisão: {len(sample)}")
    print(f"HTML: {HTML_PATH.resolve()}")
    print(f"Amostra JSONL: {SAMPLE_PATH.resolve()}")


if __name__ == "__main__":
    main()
