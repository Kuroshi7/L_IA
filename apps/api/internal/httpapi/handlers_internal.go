package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

// handleCardapioInterno: consumido pelas tools do agente Python.
// /internal/cardapio/{unidadeID}/{data}  (data="hoje" → data atual)
func (s *Server) handleCardapioInterno(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := strconv.ParseInt(chi.URLParam(r, "unidadeID"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	data := chi.URLParam(r, "data")
	if data == "" || data == "hoje" {
		data = hoje()
	}
	s.responderCardapio(w, r, unidadeID, data)
}

func (s *Server) handlePerfilInterno(w http.ResponseWriter, r *http.Request) {
	usuarioID, err := strconv.ParseInt(chi.URLParam(r, "usuarioID"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "usuarioID inválido")
		return
	}
	perfil, err := s.store.GetPerfil(r.Context(), usuarioID)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "usuário não encontrado")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao buscar perfil")
		return
	}
	writeJSON(w, http.StatusOK, perfil)
}

func (s *Server) handleMedidasInterno(w http.ResponseWriter, r *http.Request) {
	medidas, err := s.store.ListMedidasCaseiras(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao listar medidas caseiras")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"medidas": medidas})
}

// handleConsumoCalcular: recebe itens já estruturados (pela LLM) e devolve os
// nutrientes consumidos, resolvidos contra a base nutricional (cálculo determinístico).
func (s *Server) handleConsumoCalcular(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Itens []domain.ConsumoItemEntrada `json:"itens"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "corpo inválido")
		return
	}
	tot, err := s.store.CalcularConsumo(r.Context(), body.Itens)
	if err != nil {
		s.log.Error("calcular consumo", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao calcular consumo")
		return
	}
	writeJSON(w, http.StatusOK, tot)
}

// handleConsumoRegistrar: registra o consumo (e sobras) de uma refeição, pontua
// o usuário e emite `consumo.registrado` para o agregado de desperdício (regras §5/§6).
func (s *Server) handleConsumoRegistrar(w http.ResponseWriter, r *http.Request) {
	var in store.RegistroConsumoInput
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "corpo inválido")
		return
	}
	if in.UnidadeID == 0 {
		writeError(w, http.StatusBadRequest, "unidade_id é obrigatório")
		return
	}
	if len(in.Itens) == 0 {
		writeError(w, http.StatusBadRequest, "informe ao menos um item consumido")
		return
	}
	res, err := s.store.RegistrarConsumo(r.Context(), in)
	if err != nil {
		s.log.Error("registrar consumo", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao registrar consumo")
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// handleCardapioSemanaInterno: grade seg–sex para a IA responder perguntas da semana.
func (s *Server) handleCardapioSemanaInterno(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := strconv.ParseInt(chi.URLParam(r, "unidadeID"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	inicio := r.URL.Query().Get("inicio")
	if inicio == "" {
		inicio = mondayOf(time.Now()).Format("2006-01-02")
	}
	sem, err := s.store.GetCardapioSemana(r.Context(), unidadeID, inicio)
	if err != nil {
		s.log.Error("cardapio semana (interno)", "err", err)
		writeError(w, http.StatusBadRequest, "não foi possível montar a semana: "+err.Error())
		return
	}
	writeJSON(w, http.StatusOK, sem)
}

func (s *Server) handleGamificacaoInterno(w http.ResponseWriter, r *http.Request) {
	s.handleGetGamificacao(w, r)
}

// handleUsuarioPorTelegram: resolve o usuário vinculado a um chat do Telegram.
func (s *Server) handleUsuarioPorTelegram(w http.ResponseWriter, r *http.Request) {
	chatID, err := strconv.ParseInt(chi.URLParam(r, "chatID"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "chatID inválido")
		return
	}
	u, err := s.store.GetUsuarioPorTelegram(r.Context(), chatID)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "nenhum usuário vinculado a este chat")
		return
	}
	if err != nil {
		s.log.Error("usuário por telegram", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao buscar usuário")
		return
	}
	writeJSON(w, http.StatusOK, usuarioComPerfil(u))
}

// handleVincularTelegram: associa um chat do Telegram a um usuário existente.
func (s *Server) handleVincularTelegram(w http.ResponseWriter, r *http.Request) {
	usuarioID, err := strconv.ParseInt(chi.URLParam(r, "usuarioID"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "usuarioID inválido")
		return
	}
	var body struct {
		ChatID int64 `json:"chat_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.ChatID == 0 {
		writeError(w, http.StatusBadRequest, "informe chat_id")
		return
	}
	if err := s.store.VincularTelegram(r.Context(), usuarioID, body.ChatID); errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "usuário não encontrado")
		return
	} else if err != nil {
		s.log.Error("vincular telegram", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao vincular telegram")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"usuario_id": usuarioID, "chat_id": body.ChatID, "vinculado": true})
}
