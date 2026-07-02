package chat

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/tamy-ai/menu-ai/api/internal/queue"
	"github.com/tamy-ai/menu-ai/api/internal/store"
)

const windowSize = 6 // últimas 6 mensagens (3 turnos) de memória curta

type Service struct {
	store   *store.Store
	rpc     *queue.ChatClient
	timeout time.Duration
}

func New(st *store.Store, rpc *queue.ChatClient, timeout time.Duration) *Service {
	return &Service{store: st, rpc: rpc, timeout: timeout}
}

type Input struct {
	SessionID string
	UnidadeID int64
	UsuarioID *int64
	Mensagem  string
}

type Output struct {
	SessionID    string `json:"session_id"`
	Resposta     string `json:"resposta"`
	ForaDeEscopo bool   `json:"fora_de_escopo"`
}

// mensagem trafegada via RabbitMQ entre Go e o worker Python.
type rpcRequest struct {
	SessionID string      `json:"session_id"`
	UnidadeID int64       `json:"unidade_id"`
	UsuarioID *int64      `json:"usuario_id,omitempty"`
	Mensagem  string      `json:"mensagem"`
	Historico []histTurno `json:"historico"`
}

type histTurno struct {
	Papel    string `json:"papel"`
	Conteudo string `json:"conteudo"`
}

type rpcResponse struct {
	Resposta     string `json:"resposta"`
	ForaDeEscopo bool   `json:"fora_de_escopo"`
	Erro         string `json:"erro,omitempty"`
}

// Responder resolve a sessão, persiste a mensagem do usuário, delega a inferência
// ao worker de IA (RPC sobre RabbitMQ) e persiste a resposta.
func (s *Service) Responder(ctx context.Context, in Input) (Output, error) {
	sess, err := s.resolverSessao(ctx, in)
	if err != nil {
		return Output{}, err
	}

	historico, err := s.store.ListMensagens(ctx, sess.ID, windowSize)
	if err != nil {
		return Output{}, fmt.Errorf("carregar histórico: %w", err)
	}

	if err := s.store.AddMensagem(ctx, sess.ID, "user", in.Mensagem); err != nil {
		return Output{}, fmt.Errorf("persistir mensagem do usuário: %w", err)
	}

	req := rpcRequest{
		SessionID: sess.ID,
		UnidadeID: sess.UnidadeID,
		UsuarioID: sess.UsuarioID,
		Mensagem:  in.Mensagem,
	}
	for _, m := range historico {
		req.Historico = append(req.Historico, histTurno{Papel: m.Papel, Conteudo: m.Conteudo})
	}
	body, _ := json.Marshal(req)

	callCtx, cancel := context.WithTimeout(ctx, s.timeout)
	defer cancel()
	respBytes, err := s.rpc.Call(callCtx, body)
	if err != nil {
		return Output{}, fmt.Errorf("worker de IA: %w", err)
	}

	var resp rpcResponse
	if err := json.Unmarshal(respBytes, &resp); err != nil {
		return Output{}, fmt.Errorf("resposta inválida do worker: %w", err)
	}
	if resp.Erro != "" {
		return Output{}, fmt.Errorf("worker reportou erro: %s", resp.Erro)
	}

	if err := s.store.AddMensagem(ctx, sess.ID, "assistant", resp.Resposta); err != nil {
		return Output{}, fmt.Errorf("persistir resposta: %w", err)
	}

	return Output{SessionID: sess.ID, Resposta: resp.Resposta, ForaDeEscopo: resp.ForaDeEscopo}, nil
}

func (s *Service) resolverSessao(ctx context.Context, in Input) (store.Sessao, error) {
	if in.SessionID != "" {
		sess, err := s.store.GetSessao(ctx, in.SessionID)
		if err == nil {
			// sessão anônima que passou a ter usuário identificado → vincula.
			if sess.UsuarioID == nil && in.UsuarioID != nil {
				if err := s.store.VincularSessaoUsuario(ctx, sess.ID, *in.UsuarioID); err == nil {
					sess.UsuarioID = in.UsuarioID
				}
			}
			return sess, nil
		}
		// sessão informada não existe → cria uma nova abaixo
	}
	if in.UnidadeID == 0 {
		return store.Sessao{}, fmt.Errorf("unidade_id é obrigatório para iniciar uma sessão")
	}
	return s.store.CriarSessao(ctx, in.UnidadeID, in.UsuarioID, "web")
}

func (s *Service) ResetarSessao(ctx context.Context, id string) error {
	return s.store.ResetSessao(ctx, id)
}
