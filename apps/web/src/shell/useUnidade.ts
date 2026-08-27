import { useEffect, useState } from "react";
import { listarUnidadesCache } from "../lib/api";
import type { Unidade } from "../types";

/** Nome da unidade em foco, para a lateral. Silencioso em caso de falha: a
 *  ausência do nome não pode impedir a pessoa de conversar. */
export function useUnidade(unidadeId: number | null | undefined): Unidade | null {
  const [unidade, setUnidade] = useState<Unidade | null>(null);

  useEffect(() => {
    if (!unidadeId) { setUnidade(null); return; }
    let vivo = true;
    listarUnidadesCache()
      .then((us) => { if (vivo) setUnidade(us.find((u) => u.id === unidadeId) ?? null); })
      .catch(() => undefined);
    return () => { vivo = false; };
  }, [unidadeId]);

  return unidade;
}
