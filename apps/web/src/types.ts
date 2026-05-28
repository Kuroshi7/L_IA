export interface Unidade {
  id: number;
  nome: string;
  slug: string;
  ativo: boolean;
}

export interface ChatResponse {
  session_id: string;
  resposta: string;
  fora_de_escopo: boolean;
}

export interface Prato {
  id: number;
  nome: string;
  categoria: string;
  calorias: number;
  proteinas_g: number;
  is_proteina_do_dia: boolean;
}
