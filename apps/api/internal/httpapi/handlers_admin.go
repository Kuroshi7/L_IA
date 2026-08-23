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

// adminAuth exige o header X-Admin-Token quando ADMIN_TOKEN está configurado.
// Sem token configurado o gate fica desabilitado (apenas para desenvolvimento).
func (s *Server) adminAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.adminToken == "" {
			next.ServeHTTP(w, r)
			return
		}
		if r.Header.Get("X-Admin-Token") != s.adminToken {
			writeError(w, http.StatusUnauthorized, "token de admin inválido ou ausente")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func paramInt64(r *http.Request, name string) (int64, error) {
	return strconv.ParseInt(chi.URLParam(r, name), 10, 64)
}

func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) bool {
	if err := json.NewDecoder(r.Body).Decode(dst); err != nil {
		writeError(w, http.StatusBadRequest, "corpo inválido")
		return false
	}
	return true
}

// mondayOf retorna a segunda-feira da semana de t.
func mondayOf(t time.Time) time.Time {
	offset := (int(t.Weekday()) + 6) % 7
	return time.Date(t.Year(), t.Month(), t.Day()-offset, 0, 0, 0, 0, t.Location())
}

// ---------------------------------------------------------------------------
// Catálogo de alimentos
// ---------------------------------------------------------------------------

func (s *Server) handleListAlimentos(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	alimentos, err := s.store.ListAlimentos(r.Context(), unidadeID)
	if err != nil {
		s.log.Error("listar alimentos", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao listar alimentos")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"alimentos": alimentos})
}

func (s *Server) handleCreateAlimento(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	var in domain.AlimentoInput
	if !decodeJSON(w, r, &in) {
		return
	}
	if err := in.Validar(true); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	a, err := s.store.CreateAlimento(r.Context(), unidadeID, in)
	if err != nil {
		s.log.Error("criar alimento", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao criar alimento")
		return
	}
	writeJSON(w, http.StatusCreated, a)
}

func (s *Server) handleUpdateAlimento(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "alimentoID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "alimentoID inválido")
		return
	}
	var in domain.AlimentoInput
	if !decodeJSON(w, r, &in) {
		return
	}
	if err := in.Validar(false); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	a, err := s.store.UpdateAlimento(r.Context(), id, in)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "alimento não encontrado")
		return
	}
	if err != nil {
		s.log.Error("atualizar alimento", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao atualizar alimento")
		return
	}
	writeJSON(w, http.StatusOK, a)
}

func (s *Server) handleSetAlimentoAtivo(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "alimentoID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "alimentoID inválido")
		return
	}
	var body struct {
		Ativo bool `json:"ativo"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if err := s.store.SetAlimentoAtivo(r.Context(), id, body.Ativo); errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "alimento não encontrado")
		return
	} else if err != nil {
		s.log.Error("ativar/desativar alimento", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao alterar o alimento")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "ativo": body.Ativo})
}

// ---------------------------------------------------------------------------
// Referência nutricional (medidas caseiras)
// ---------------------------------------------------------------------------

func (s *Server) handleSearchNutri(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	refs, err := s.store.SearchNutriAlimentos(r.Context(), q, limit)
	if err != nil {
		s.log.Error("buscar nutri-alimentos", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao buscar referência nutricional")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"nutri_alimentos": refs})
}

func (s *Server) handleGetNutri(w http.ResponseWriter, r *http.Request) {
	id, err := paramInt64(r, "nutriID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "id inválido")
		return
	}
	ref, err := s.store.GetNutriAlimentoComPorcoes(r.Context(), id)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, "referência não encontrada")
		return
	}
	if err != nil {
		s.log.Error("buscar nutri-alimento", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao buscar referência nutricional")
		return
	}
	writeJSON(w, http.StatusOK, ref)
}

func (s *Server) handleCreateNutri(w http.ResponseWriter, r *http.Request) {
	var in domain.NutriRefInput
	if !decodeJSON(w, r, &in) {
		return
	}
	if in.Nome == "" || len(in.Porcoes) == 0 {
		writeError(w, http.StatusBadRequest, "informe nome e ao menos uma medida caseira")
		return
	}
	ref, err := s.store.CreateNutriAlimento(r.Context(), in)
	if err != nil {
		s.log.Error("criar nutri-alimento", "err", err)
		writeError(w, http.StatusInternalServerError, "erro ao criar referência nutricional")
		return
	}
	writeJSON(w, http.StatusCreated, ref)
}

// ---------------------------------------------------------------------------
// Cardápio semanal
// ---------------------------------------------------------------------------

func (s *Server) handleGetCardapioSemana(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := paramInt64(r, "unidadeID")
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
		s.log.Error("cardapio semana", "err", err)
		writeError(w, http.StatusBadRequest, "não foi possível montar a semana")
		return
	}
	writeJSON(w, http.StatusOK, sem)
}

func (s *Server) handleSetCardapioItens(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	data := chi.URLParam(r, "data")
	var body struct {
		Itens []domain.CardapioItemInput `json:"itens"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	proteinas := 0
	for _, it := range body.Itens {
		if it.IsProteinaDoDia {
			proteinas++
		}
	}
	if proteinas > 1 {
		writeError(w, http.StatusBadRequest, "no máximo 1 proteína do dia por dia")
		return
	}
	dia, err := s.store.SetCardapioItens(r.Context(), unidadeID, data, body.Itens)
	if err != nil {
		s.log.Error("set cardapio itens", "err", err)
		writeError(w, http.StatusBadRequest, "não foi possível salvar o cardápio")
		return
	}
	writeJSON(w, http.StatusOK, dia)
}

func (s *Server) handleCopiarSemana(w http.ResponseWriter, r *http.Request) {
	unidadeID, err := paramInt64(r, "unidadeID")
	if err != nil {
		writeError(w, http.StatusBadRequest, "unidadeID inválido")
		return
	}
	var body struct {
		Origem  string `json:"origem"`
		Destino string `json:"destino"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if body.Origem == "" || body.Destino == "" {
		writeError(w, http.StatusBadRequest, "informe as datas de origem e destino (segundas-feiras)")
		return
	}
	sem, err := s.store.CopiarSemana(r.Context(), unidadeID, body.Origem, body.Destino)
	if err != nil {
		s.log.Error("copiar semana", "err", err)
		writeError(w, http.StatusBadRequest, "não foi possível copiar a semana")
		return
	}
	writeJSON(w, http.StatusOK, sem)
}
