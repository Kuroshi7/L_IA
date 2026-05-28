package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/tamy-ai/menu-ai/api/internal/chat"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"erro": msg})
}

func hoje() string { return time.Now().Format("2006-01-02") }

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "servico": "menu-ai api"})
}

func (s *Server) handleListUnidades(w http.ResponseWriter, r *http.Request) {
	unidades, err := s.store.ListUnidades(r.Context())
	if err != nil {
		s.log.Error("listar unidades", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao listar unidades")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"unidades": unidades})
}

func (s *Server) handleCardapioPublico(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := strconv.ParseInt(chi.URLParam(r, "unidadeID"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	data := r.URL.Query().Get("data")
	if data == "" || data == "hoje" {
		data = hoje()
	}
	s.responderCardapio(w, r, unidadeID, data)
}

func (s *Server) responderCardapio(w http.ResponseWriter, r *http.Request, unidadeID int64, data string) {
	dia, err := s.store.GetCardapioDoDia(r.Context(), unidadeID, data)
	if errors.Is(err, store.ErrNotFound) {
		writeJSON(w, http.StatusOK, map[string]any{"unidade_id": unidadeID, "data": data, "pratos": []any{}})
		return
	}
	if err != nil {
		s.log.Error("cardapio do dia", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao buscar cardápio")
		return
	}
	writeJSON(w, http.StatusOK, dia)
}

func (s *Server) handleSaudacao(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"mensagem": "Olá! Sou a Lia 🍽️ Posso te ajudar a escolher uma refeição do cardápio de hoje. " +
			"Tem alguma restrição (vegetariano, sem lactose, celíaco) ou alergia que eu deva considerar?",
	})
}

type chatBody struct {
	UnidadeID int64  `json:"unidade_id"`
	SessionID string `json:"session_id"`
	Mensagem  string `json:"mensagem"`
}

func (s *Server) handleChat(w http.ResponseWriter, r *http.Request) {
	var body chatBody
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "corpo inválido")
		return
	}
	if body.Mensagem == "" {
		writeError(w, http.StatusBadRequest, "mensagem é obrigatória")
		return
	}

	out, err := s.chat.Responder(r.Context(), chat.Input{
		SessionID: body.SessionID,
		UnidadeID: body.UnidadeID,
		Mensagem:  body.Mensagem,
	})
	if err != nil {
		s.log.Error("chat", "err", err)
		writeError(w, http.StatusBadGateway, "não foi possível processar a mensagem agora")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) handleResetChat(w http.ResponseWriter, r *http.Request) {
	sessionID := chi.URLParam(r, "sessionID")
	if err := s.chat.ResetarSessao(r.Context(), sessionID); err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao resetar sessão")
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"reset": true})
}
