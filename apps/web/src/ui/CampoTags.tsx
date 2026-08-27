import { useId, useRef, useState } from "react";
import Icone from "./Icone";

/**
 * Entrada de termos como etiquetas.
 *
 * Substitui os campos "separados por vírgula" do cadastro. O problema deles não
 * era só estético: "separadas por vírgula" é uma instrução que a pessoa lê e
 * ignora, e o que ela escreve ("não posso comer leite") vira UM termo só, que
 * nunca casa com o filtro determinístico do backend. Com etiqueta, cada termo
 * fica visível como uma unidade — a pessoa vê que escreveu uma frase quando
 * queria escrever três palavras.
 *
 * As sugestões são exemplos, não um vocabulário fechado: o casamento acontece
 * contra o que o gestor cadastrou em `restricoes_atendidas` de cada alimento, e
 * isso varia por unidade. Fechar a lista aqui só mudaria o lugar da falha
 * silenciosa (ver WEB-03 em docs/tickets-revisao-produto.md, que continua
 * aberto: a correção de verdade é o vocabulário vir do backend).
 */
interface Props {
  rotulo: string;
  valores: string[];
  aoMudar: (v: string[]) => void;
  sugestoes?: string[];
  ajuda?: string;
  placeholder?: string;
}

export default function CampoTags({ rotulo, valores, aoMudar, sugestoes, ajuda, placeholder }: Props) {
  const [rascunho, setRascunho] = useState("");
  const campoRef = useRef<HTMLInputElement>(null);
  const id = useId();

  function juntar(bruto: string) {
    // Vírgula continua funcionando para quem já tem o hábito — colar
    // "arroz, feijão" cria duas etiquetas.
    const novos = bruto
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t && !valores.some((v) => v.toLowerCase() === t.toLowerCase()));
    if (novos.length) aoMudar([...valores, ...novos]);
    setRascunho("");
  }

  function aoTeclar(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      juntar(rascunho);
    } else if (e.key === "Backspace" && !rascunho && valores.length) {
      // Apagar com o campo vazio remove a última etiqueta: é o que todo mundo
      // tenta fazer sem pensar.
      aoMudar(valores.slice(0, -1));
    }
  }

  const disponiveis = (sugestoes ?? []).filter(
    (s) => !valores.some((v) => v.toLowerCase() === s.toLowerCase()),
  );

  return (
    <div className="campo">
      <label className="campo-rotulo" htmlFor={id}>{rotulo}</label>

      <div className="tags" onClick={() => campoRef.current?.focus()}>
        {valores.map((v) => (
          <span className="tag" key={v}>
            {v}
            <button
              type="button"
              className="tag__x"
              onClick={() => aoMudar(valores.filter((x) => x !== v))}
              aria-label={`Remover ${v}`}
            >
              <Icone nome="remover" tam={12} />
            </button>
          </span>
        ))}
        <input
          id={id}
          ref={campoRef}
          className="tags__campo"
          value={rascunho}
          onChange={(e) => setRascunho(e.target.value)}
          onKeyDown={aoTeclar}
          onBlur={() => juntar(rascunho)}
          placeholder={valores.length ? "" : placeholder}
        />
      </div>

      {disponiveis.length > 0 && (
        <div className="tags-sugestoes">
          <span className="campo-ajuda">Comuns:</span>
          {disponiveis.map((s) => (
            <button type="button" key={s} className="pilula" onClick={() => juntar(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      {ajuda && <span className="campo-ajuda">{ajuda}</span>}
    </div>
  );
}
