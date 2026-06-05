"""ETL reproduzível da Tabela de Medidas Caseiras (PDF escaneado) -> nutricao.json.

Como as páginas são imagens, usa a visão da LLM (Anthropic) para extrair cada
página em JSON estruturado, normaliza os rótulos de medida e faz merge no
seed (apps/api/seed/nutricao.json), sem sobrescrever o núcleo verificado.

Requisitos:
  pip install -r requirements-etl.txt
  export ANTHROPIC_API_KEY=sk-ant-...
  coloque o PDF em docs/sources/tabela-medidas-caseiras.pdf (ou aponte --pdf)

Uso (extração em lotes, recomendado):
  python -m app.nutrition.etl --start 3 --end 12
  python -m app.nutrition.etl --start 13 --end 30
  ...
Depois rode o seed do Go para carregar no banco.
"""

import argparse
import base64
import json
import os
import re
from pathlib import Path

from app.nutrition.medidas import normalizar, parse_medida_label

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PDF = ROOT / "docs" / "sources" / "tabela-medidas-caseiras.pdf"
OUTPUT = ROOT / "apps" / "api" / "seed" / "nutricao.json"

PROMPT = """Você recebe a imagem de UMA página de uma tabela nutricional brasileira de medidas caseiras.

As colunas, nesta ordem, são:
ALIMENTO (e abaixo a "Medida caseira") | Quant. (g/mL) | Energia (kcal) | Ptn. (g) | Gli. (g, = CARBOIDRATO) | Lip. (g, = GORDURA) | Ca (mg) | Fe (mg) | Vit. C (mg) | Vit. A (µg RE) | Fonte

Cada ALIMENTO (em negrito/maiúsculas) tem uma linha de referência (Quant. = 100,0) e várias linhas indentadas de porções (a primeira coluna é o rótulo da medida caseira, ex: "COL S CH PICADO", "CO M CH", "PT F R", "UND M", "FILÉ G").

Extraia TODOS os alimentos e porções da página em JSON, exatamente neste formato:
{"alimentos":[
  {"nome":"ARROZ COZIDO","fonte":"IBGE","porcoes":[
     {"medida_label":"100g","quantidade_g":100.0,"kcal":164.0,"proteina_g":2.30,"carboidrato_g":32.30,"gordura_g":2.90,"calcio_mg":3.0,"ferro_mg":0.80,"vit_c_mg":null,"vit_a_ug":null},
     {"medida_label":"COL S CH","quantidade_g":25.0,"kcal":41.0,"proteina_g":0.58,"carboidrato_g":8.07,"gordura_g":0.73,"calcio_mg":0.75,"ferro_mg":0.20,"vit_c_mg":null,"vit_a_ug":null}
  ]}
]}

Regras IMPORTANTES:
- Vírgula decimal vira ponto (2,30 -> 2.30).
- Travessão "—", "( )" ou célula vazia viram null.
- "Gli." é o CARBOIDRATO; "Lip." é a GORDURA.
- Para a linha de 100g use medida_label "100g".
- NÃO invente valores; transcreva exatamente o que está na imagem.
- Responda APENAS o JSON, sem texto antes ou depois.
"""


def _render_page_png(pdf_path: Path, page_index: int) -> bytes:
    try:
        import fitz  # pymupdf
    except ImportError as e:
        raise SystemExit("pymupdf não instalado. Rode: pip install -r requirements-etl.txt") from e
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pix = page.get_pixmap(dpi=200)
    return pix.tobytes("png")


def _extract_page(png: bytes, model: str) -> dict:
    try:
        import anthropic
    except ImportError as e:
        raise SystemExit("anthropic não instalado. Rode: pip install -r requirements-etl.txt") from e
    client = anthropic.Anthropic()
    b64 = base64.standard_b64encode(png).decode("ascii")
    msg = client.messages.create(
        model=model,
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


def _load_output() -> dict:
    if OUTPUT.exists():
        return json.loads(OUTPUT.read_text(encoding="utf-8"))
    return {"medida_aliases": [], "alimentos": []}


def _merge(out: dict, extraidos: list[dict]) -> int:
    por_nome = {normalizar(a["nome"]): a for a in out["alimentos"]}
    novos = 0
    for a in extraidos:
        nome = a.get("nome", "").strip()
        if not nome:
            continue
        chave = normalizar(nome)
        if chave in por_nome:
            continue  # preserva o núcleo verificado / não duplica
        porcoes = []
        for p in a.get("porcoes", []):
            label = (p.get("medida_label") or "").strip()
            if not label or p.get("quantidade_g") in (None, 0):
                continue
            meta = parse_medida_label(label) if label != "100g" else {}
            porcoes.append({
                "medida_label": label,
                "medida_cod": meta.get("medida_cod"),
                "tamanho": meta.get("tamanho"),
                "estado": meta.get("estado"),
                "quantidade_g": p.get("quantidade_g"),
                "kcal": p.get("kcal"),
                "proteina_g": p.get("proteina_g"),
                "carboidrato_g": p.get("carboidrato_g"),
                "gordura_g": p.get("gordura_g"),
                "calcio_mg": p.get("calcio_mg"),
                "ferro_mg": p.get("ferro_mg"),
                "vit_c_mg": p.get("vit_c_mg"),
                "vit_a_ug": p.get("vit_a_ug"),
            })
        if not porcoes:
            continue
        novo = {
            "nome": nome.title(),
            "categoria": a.get("categoria", ""),
            "fonte": a.get("fonte", ""),
            "aliases": [normalizar(nome)],
            "porcoes": porcoes,
        }
        out["alimentos"].append(novo)
        por_nome[chave] = novo
        novos += 1
    return novos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default=str(os.getenv("NUTRI_PDF_PATH", DEFAULT_PDF)))
    ap.add_argument("--start", type=int, default=3, help="primeira página (1-based)")
    ap.add_argument("--end", type=int, default=66, help="última página (1-based)")
    ap.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"PDF não encontrado: {pdf_path}. Coloque-o lá ou use --pdf.")

    out = _load_output()
    total_novos = 0
    for page_1based in range(args.start, args.end + 1):
        png = _render_page_png(pdf_path, page_1based - 1)
        try:
            data = _extract_page(png, args.model)
        except Exception as e:  # página problemática não derruba o lote
            print(f"[p{page_1based}] falha na extração: {type(e).__name__}: {e}")
            continue
        novos = _merge(out, data.get("alimentos", []))
        total_novos += novos
        print(f"[p{page_1based}] +{novos} alimentos (total acumulado: {len(out['alimentos'])})")

    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK — {total_novos} novos alimentos adicionados. Arquivo: {OUTPUT}")
    print("Agora rode o seed do Go para carregar no banco (docker compose run --rm api-seed).")


if __name__ == "__main__":
    main()
