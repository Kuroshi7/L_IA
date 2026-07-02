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

// ---- Usuário e perfil nutricional ----

export type Sexo = "M" | "F" | "O";

export type NivelAtividade = "sedentario" | "leve" | "moderado" | "intenso" | "muito_intenso";

export interface Usuario {
  id: number;
  nome: string;
  peso_kg?: number | null;
  altura_cm?: number | null;
  idade?: number | null;
  sexo?: Sexo | null;
  nivel_atividade?: NivelAtividade | null;
  restricoes: string[] | null;
  preferencias: string[] | null;
  alergias: string[] | null;
  unidade_id?: number | null;
}

export interface UsuarioInput {
  nome: string;
  peso_kg?: number;
  altura_cm?: number;
  idade?: number;
  sexo?: Sexo;
  nivel_atividade?: NivelAtividade;
  restricoes: string[];
  preferencias: string[];
  alergias: string[];
  unidade_id?: number;
}

export interface PerfilNutricional {
  nome: string;
  restricoes: string[] | null;
  preferencias: string[] | null;
  alergias: string[] | null;
  imc?: number | null;
  classificacao_imc?: string;
  meta_calorica_kcal?: number | null;
}

export interface UsuarioComPerfil {
  usuario: Usuario;
  perfil: PerfilNutricional;
}

// ---- Gamificação e ranking ----

export interface Gamificacao {
  usuario_id: number;
  pontos: number;
  nivel: number;
  streak_dias: number;
  ultimo_registro?: string | null;
}

export interface GamificacaoEvento {
  id: number;
  pontos: number;
  motivo: string;
  created_at: string;
}

export interface GamificacaoResumo {
  gamificacao: Gamificacao;
  eventos: GamificacaoEvento[] | null;
}

export interface RankingEntry {
  usuario_id: number;
  nome: string;
  pontos: number;
  nivel: number;
}

// ---- Admin: usuários ----

export interface AdminUsuario {
  id: number;
  nome: string;
  unidade_id?: number | null;
  restricoes: string[] | null;
  alergias: string[] | null;
  pontos: number;
  nivel: number;
  streak_dias: number;
  registros_consumo: number;
}

// ---- Admin: desperdício ----

export type ClassificacaoDesperdicio = "otimo" | "bom" | "atencao" | "critico";

export interface DesperdicioDia {
  data: string;
  refeicoes: number;
  consumido_g: number;
  consumido_kcal: number;
  resto_g: number;
  resto_kcal: number;
}

export interface AlimentoDesperdicado {
  alimento: string;
  ocorrencias: number;
  resto_g: number;
  resto_kcal: number;
}

export interface DesperdicioRelatorio {
  unidade_id: number;
  de: string;
  ate: string;
  refeicoes: number;
  consumido_g: number;
  resto_g: number;
  resto_kcal: number;
  indice_resto_perc: number;
  classificacao: ClassificacaoDesperdicio;
  resto_per_capita_g: number;
  dias: DesperdicioDia[] | null;
  top_desperdicados: AlimentoDesperdicado[] | null;
}
