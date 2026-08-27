import { useCallback, useEffect, useState } from "react";
import { aplicarPreferencia, lerPreferencia, salvarPreferencia, type Preferencia } from "./tema";

/** Preferência de tema + reação à troca no sistema operacional. */
export function useTema(): [Preferencia, (p: Preferencia) => void] {
  const [pref, setPref] = useState<Preferencia>(lerPreferencia);

  useEffect(() => {
    aplicarPreferencia(pref);
    if (pref !== "sistema") return;
    // Só interessa ouvir o SO enquanto a escolha for "seguir o sistema".
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const aoTrocar = () => aplicarPreferencia("sistema");
    mq.addEventListener("change", aoTrocar);
    return () => mq.removeEventListener("change", aoTrocar);
  }, [pref]);

  const escolher = useCallback((p: Preferencia) => {
    setPref(p);
    salvarPreferencia(p);
  }, []);

  return [pref, escolher];
}
