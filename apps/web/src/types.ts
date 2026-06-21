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

// ---- Admin ----

export interface Alimento {
  id: number;
  unidade_id: number;
  nome: string;
  categoria: string;
  ingredientes: string[];
  alergenos: string[];
  restricoes_atendidas: string[];
  nao_indicado_para: string[];
  calorias: number;
  proteinas_g: number;
  carboidratos_g: number;
  gorduras_g: number;
  ativo: boolean;
  is_proteina_do_dia: boolean;
  nutri_alimento_id?: number | null;
}

export interface CardapioDia {
  id: number;
  unidade_id: number;
  data: string;
  dia_semana: string;
  pratos: Alimento[];
}

export interface CardapioSemana {
  unidade_id: number;
  inicio: string;
  dias: CardapioDia[];
}

export interface NutriPorcao {
  id?: number;
  alimento_id?: number;
  medida_label: string;
  medida_cod?: string;
  quantidade_g: number;
  kcal: number;
  proteina_g: number;
  carboidrato_g: number;
  gordura_g: number;
}

export interface NutriAlimento {
  id: number;
  nome: string;
  categoria: string;
  fonte: string;
  aliases: string[];
}

export interface NutriAlimentoDetalhe extends NutriAlimento {
  porcoes: NutriPorcao[];
}

// Payloads de criação/edição

export interface PorcaoInput {
  medida_label: string;
  medida_cod?: string;
  quantidade_g: number;
  kcal: number;
  proteina_g: number;
  carboidrato_g: number;
  gordura_g: number;
}

export interface NutriRefInput {
  nome: string;
  categoria?: string;
  aliases?: string[];
  porcoes: PorcaoInput[];
}

export interface AlimentoInput {
  nome: string;
  categoria: string;
  ingredientes: string[];
  alergenos: string[];
  restricoes_atendidas: string[];
  nao_indicado_para: string[];
  calorias: number;
  proteinas_g: number;
  carboidratos_g: number;
  gorduras_g: number;
  ativo: boolean;
  nutri_alimento_id?: number | null;
  nova_ref?: NutriRefInput | null;
}

export interface CardapioItemInput {
  alimento_id: number;
  is_proteina_do_dia: boolean;
}
