package httpapi

import (
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/tamy-ai/menu-ai/api/internal/domain"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

// ---------------------------------------------------------------------------
// Gestão de unidades (admin)
// ---------------------------------------------------------------------------

func (s *Server) handleListUnidadesAdmin(w http.ResponseWriter, r *http.Request) {
	unidades, err := s.store.ListUnidadesAdmin(r.Context())
	if err != nil {
		s.log.Error("listar unidades (admin)", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao listar unidades")
		return
	}
	if unidades == nil {
		unidades = []domain.Unidade{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"unidades": unidades})
}

func (s *Server) handleCreateUnidade(w http.ResponseWriter, r *http.Request) {
	var in domain.UnidadeInput
	if !decodeJSON(w, r, &in) {
		return
	}
	if err := in.Validar(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	u, err := s.store.CreateUnidade(r.Context(), in)
	if errors.Is(err, store.ErrSlugEmUso) {
		writeError(w, http.StatusConflict, "já existe uma unidade com esse slug")
		return
	}
	if err != nil {
		s.log.Error("criar unidade", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao criar unidade")
		return
	}
	writeJSON(w, http.StatusCreated, u)
}

func (s *Server) handleUpdateUnidade(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	var in domain.UnidadeInput
	if !decodeJSON(w, r, &in) {
		return
	}
	if err := in.Validar(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	u, err := s.store.UpdateUnidade(r.Context(), id, in)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "unidade não encontrada")
		return
	}
	if errors.Is(err, store.ErrSlugEmUso) {
		writeError(w, http.StatusConflict, "já existe uma unidade com esse slug")
		return
	}
	if err != nil {
		s.log.Error("atualizar unidade", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao atualizar unidade")
		return
	}
	writeJSON(w, http.StatusOK, u)
}

func (s *Server) handleSetUnidadeAtivo(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	var body struct {
		Ativo bool `json:"ativo"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if err := s.store.SetUnidadeAtivo(r.Context(), id, body.Ativo); errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "unidade não encontrada")
		return
	} else if err != nil {
		s.log.Error("ativar/desativar unidade", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao alterar a unidade")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "ativo": body.Ativo})
}

// ---------------------------------------------------------------------------
// Usuários (admin) e dashboard de desperdício
// ---------------------------------------------------------------------------

func (s *Server) handleListUsuariosAdmin(w http.ResponseWriter, r *http.Request) {
	var unidadeID int64
	if q := r.URL.Query().Get("unidade_id"); q != "" {
		id, err := strconv.ParseInt(q, 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "unidade_id inválido")
			return
		}
		unidadeID = id
	}
	usuarios, err := s.store.ListUsuariosAdmin(r.Context(), unidadeID)
	if err != nil {
		s.log.Error("listar usuários (admin)", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao listar usuários")
		return
	}
	if usuarios == nil {
		usuarios = []map[string]any{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"usuarios": usuarios})
}

// handleDesperdicio: visão de desperdício da unidade num período (default: últimos 14 dias).
func (s *Server) handleDesperdicio(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	ate := r.URL.Query().Get("ate")
	if ate == "" {
		ate = time.Now().Format("2006-01-02")
	}
	de := r.URL.Query().Get("de")
	if de == "" {
		fim, _ := time.Parse("2006-01-02", ate)
		de = fim.AddDate(0, 0, -13).Format("2006-01-02")
	}
	resumo, err := s.store.GetDesperdicioResumo(r.Context(), unidadeID, de, ate)
	if err != nil {
		s.log.Error("desperdício", "err", err)
		writeError(w, http.StatusBadRequest, "não foi possível montar o resumo: "+err.Error())
		return
	}
	if resumo.Dias == nil {
		resumo.Dias = []domain.DesperdicioDia{}
	}
	if resumo.TopDesperdicados == nil {
		resumo.TopDesperdicados = []domain.AlimentoDesperdicado{}
	}
	writeJSON(w, http.StatusOK, resumo)
}
