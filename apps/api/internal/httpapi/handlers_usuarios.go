package httpapi

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

// usuarioComPerfil devolve o usuário + o perfil derivado (IMC, meta calórica),
// para o front exibir o resultado do cadastro imediatamente.
func usuarioComPerfil(u domain.Usuario) map[string]any {
	return map[string]any{"usuario": u, "perfil": u.MontarPerfil()}
}

func (s *Server) handleCreateUsuario(w http.ResponseWriter, r *http.Request) {
	var in domain.UsuarioInput
	if !decodeJSON(w, r, &in) {
		return
	}
	if err := in.Validar(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	u, err := s.store.CreateUsuario(r.Context(), in)
	if err != nil {
		s.log.Error("criar usuário", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao criar usuário")
		return
	}
	writeJSON(w, http.StatusCreated, usuarioComPerfil(u))
}

func (s *Server) handleGetUsuario(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "usuarioID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "usuarioID inválido")
		return
	}
	u, err := s.store.GetUsuario(r.Context(), id)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "usuário não encontrado")
		return
	}
	if err != nil {
		s.log.Error("buscar usuário", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao buscar usuário")
		return
	}
	writeJSON(w, http.StatusOK, usuarioComPerfil(u))
}

func (s *Server) handleUpdateUsuario(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "usuarioID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "usuarioID inválido")
		return
	}
	var in domain.UsuarioInput
	if !decodeJSON(w, r, &in) {
		return
	}
	if err := in.Validar(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	u, err := s.store.UpdateUsuario(r.Context(), id, in)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "usuário não encontrado")
		return
	}
	if err != nil {
		s.log.Error("atualizar usuário", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao atualizar usuário")
		return
	}
	writeJSON(w, http.StatusOK, usuarioComPerfil(u))
}

func (s *Server) handleGetGamificacao(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "usuarioID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "usuarioID inválido")
		return
	}
	g, eventos, err := s.store.GetGamificacao(r.Context(), id)
	if err != nil {
		s.log.Error("buscar gamificação", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao buscar gamificação")
		return
	}
	if eventos == nil {
		eventos = []domain.EventoPontuacao{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"gamificacao": g, "eventos": eventos})
}

func (s *Server) handleGetRanking(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	ranking, err := s.store.GetRanking(r.Context(), unidadeID, limit)
	if err != nil {
		s.log.Error("ranking", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao montar ranking")
		return
	}
	if ranking == nil {
		ranking = []domain.RankingEntry{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"ranking": ranking})
}
