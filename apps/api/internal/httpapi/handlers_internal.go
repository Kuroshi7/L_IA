package httpapi

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"

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
