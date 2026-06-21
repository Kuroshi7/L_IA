// Utilitários de data em horário local (evita o shift de fuso do toISOString).

export function fmtISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseISO(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

// mondayISO retorna a segunda-feira (YYYY-MM-DD) da semana da data informada.
export function mondayISO(d: Date): string {
  const offset = (d.getDay() + 6) % 7; // 0 = segunda
  return fmtISO(new Date(d.getFullYear(), d.getMonth(), d.getDate() - offset));
}

export function addDaysISO(iso: string, n: number): string {
  const d = parseISO(iso);
  d.setDate(d.getDate() + n);
  return fmtISO(d);
}

// rotuloCurto: "15/06" para cabeçalhos da grade.
export function rotuloCurto(iso: string): string {
  const d = parseISO(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}
