#!/usr/bin/env bash
# Demonstração local: preserva o .env existente e os dados já cadastrados.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v docker >/dev/null || { echo "Instale e abra o Docker antes de continuar." >&2; exit 1; }
docker compose version >/dev/null
docker info >/dev/null 2>&1 || { echo "Abra o Docker ou verifique o acesso ao serviço Docker." >&2; exit 1; }

action="${1:-iniciar}"
case "$action" in
  iniciar|parar|status|logs) ;;
  *) echo "Uso: ./demo.sh [iniciar|parar|status|logs]" >&2; exit 1 ;;
esac
if [[ ! -f .env ]]; then
  [[ "$action" == iniciar ]] || { echo "Execute ./demo.sh primeiro." >&2; exit 1; }
  (umask 077; cp .env.demo.example .env)
fi
# Lê valores simples do .env sem executar seu conteúdo.
value() {
  local line found=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    if [[ "$line" == "$1="* ]]; then found="${line#*=}"; fi
  done < .env
  found="${found%\"}"; found="${found#\"}"
  found="${found%\'}"; found="${found#\'}"
  printf '%s' "$found"
}
export DEMO_MODE=1
compose=(docker compose --project-name lia --env-file .env -f deploy/docker-compose.yml)
case "$action" in
  parar) "${compose[@]}" stop; exit ;;
  status) "${compose[@]}" ps; exit ;;
  logs) "${compose[@]}" logs --tail=80 api ai-worker api-worker; exit ;;
esac
provider="${LLM_PROVIDER:-$(value LLM_PROVIDER)}"
provider="${provider:-ollama}"
if [[ "$provider" == anthropic && -z "${ANTHROPIC_API_KEY:-$(value ANTHROPIC_API_KEY)}" ]]; then
  if [[ ! -t 0 ]]; then
    echo "Preencha ANTHROPIC_API_KEY no .env e execute ./demo.sh novamente." >&2
    exit 1
  fi
  read -r -s -p "Cole sua chave Anthropic (não será exibida): " demo_key
  printf '\n'
  [[ -n "$demo_key" ]] || { echo "Chave vazia. Nenhum serviço foi iniciado." >&2; exit 1; }
  # A última atribuição prevalece; mantém o restante do arquivo intacto.
  printf 'ANTHROPIC_API_KEY=%s\n' "$demo_key" >> .env
  chmod 600 .env
  unset demo_key
fi
printf '\nPreparando a demonstração. A primeira execução baixa imagens e pode demorar.\n'
"${compose[@]}" up -d --build --wait --wait-timeout 180 postgres rabbitmq ollama api ai-api web
# Os workers não têm servidor HTTP; --wait é reservado aos serviços com healthcheck.
"${compose[@]}" up -d --build api-worker ai-worker
# Só popula um banco vazio: execuções seguintes preservam catálogo e perfis.
units=$("${compose[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM unidades"')
if [[ "$units" == 0 ]]; then
  "${compose[@]}" run --rm api-seed
fi
embed_provider="${EMBED_PROVIDER:-$(value EMBED_PROVIDER)}"
if [[ "${embed_provider:-ollama}" == ollama ]]; then
  embed_model="${EMBED_MODEL:-$(value EMBED_MODEL)}"
  "${compose[@]}" exec -T ollama ollama pull "${embed_model:-nomic-embed-text}"
fi
if [[ "$provider" == ollama ]]; then
  model="${OLLAMA_MODEL:-$(value OLLAMA_MODEL)}"
  "${compose[@]}" exec -T ollama ollama pull "${model:-llama3.2}"
fi
chunks=$("${compose[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM embeddings"')
if [[ "$chunks" == 0 ]]; then
  "${compose[@]}" run --rm ai-indexer
fi
port="${MENUAI_WEB_PORT:-$(value MENUAI_WEB_PORT)}"
printf '\nDemonstração iniciada: http://localhost:%s\n' "${port:-5273}"
printf 'No site, escolha Refeitório Central e use o perfil de demonstração ou crie seu perfil.\n'
printf 'Administração: /admin — token local: valor ADMIN_TOKEN do .env (padrão dev-admin).\n'
printf 'Dados existentes foram preservados. Para parar: ./demo.sh parar\n'
