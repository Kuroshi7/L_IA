import { useMemo, type ReactNode } from "react";

/**
 * Renderiza a resposta da Lia.
 *
 * Não é um parser de Markdown: é o subconjunto que o modelo realmente produz —
 * negrito, itálico, listas com marcador e listas numeradas. Trazer uma
 * biblioteca de Markdown completa aqui significaria aceitar HTML arbitrário
 * vindo do LLM (XSS via resposta do modelo, que é entrada externa como
 * qualquer outra) ou carregar um sanitizador junto. Um renderizador fechado, que
 * só sabe produzir texto e três tags, não tem essa superfície: nada do que o
 * modelo escrever vira marcação além do previsto aqui.
 */

/** Aplica **negrito**, *itálico* e _itálico_ dentro de uma linha. */
function inline(texto: string, chave: string): ReactNode[] {
  const saida: ReactNode[] = [];
  let buffer = "";
  let i = 0;

  const despejar = () => {
    if (buffer) { saida.push(buffer); buffer = ""; }
  };

  while (i < texto.length) {
    const negrito = texto.startsWith("**", i);
    const italico = !negrito && (texto[i] === "*" || texto[i] === "_");

    if (negrito) {
      const fim = texto.indexOf("**", i + 2);
      if (fim > i + 2) {
        despejar();
        saida.push(<strong key={`${chave}-b${i}`}>{texto.slice(i + 2, fim)}</strong>);
        i = fim + 2;
        continue;
      }
    } else if (italico) {
      const marca = texto[i];
      const fim = texto.indexOf(marca, i + 1);
      // Exige conteúdo entre as marcas para não transformar um sublinhado
      // solto (nome_de_arquivo) em itálico.
      if (fim > i + 1) {
        despejar();
        saida.push(<em key={`${chave}-i${i}`}>{texto.slice(i + 1, fim)}</em>);
        i = fim + 1;
        continue;
      }
    }

    buffer += texto[i];
    i++;
  }

  despejar();
  return saida;
}

const MARCADOR = /^[-•·*]\s+/;
const NUMERADA = /^\d+[.)]\s+/;

export default function Texto({ conteudo }: { conteudo: string }) {
  const blocos = useMemo(() => {
    const saida: ReactNode[] = [];
    let itens: string[] = [];
    let ordenada = false;

    const fecharLista = () => {
      if (!itens.length) return;
      const filhos = itens.map((t, i) => <li key={i}>{inline(t, `l${saida.length}-${i}`)}</li>);
      saida.push(
        ordenada
          ? <ol key={`ol-${saida.length}`}>{filhos}</ol>
          : <ul key={`ul-${saida.length}`}>{filhos}</ul>,
      );
      itens = [];
    };

    for (const bruta of conteudo.split("\n")) {
      const linha = bruta.trim();

      if (MARCADOR.test(linha)) {
        if (ordenada) fecharLista();
        ordenada = false;
        itens.push(linha.replace(MARCADOR, ""));
      } else if (NUMERADA.test(linha)) {
        if (!ordenada) fecharLista();
        ordenada = true;
        itens.push(linha.replace(NUMERADA, ""));
      } else if (linha === "") {
        fecharLista();
      } else {
        fecharLista();
        saida.push(<p key={`p-${saida.length}`}>{inline(linha, `p${saida.length}`)}</p>);
      }
    }
    fecharLista();
    return saida;
  }, [conteudo]);

  return <div className="fmt">{blocos}</div>;
}
