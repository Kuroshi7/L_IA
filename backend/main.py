from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from cardapio import get_cardapio_semana, get_pratos_do_dia
from chat import processar_mensagem
from models import MensagemRequest, MensagemResponse
from prompts import MENSAGEM_INICIAL
from sessions import resetar

app = FastAPI(title="Lia Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def raiz():
    return {"status": "ok", "servico": "Apélia Chat API"}


@app.get("/cardapio/hoje")
def cardapio_hoje():
    pratos = get_pratos_do_dia("hoje")
    return {"pratos": pratos, "total": len(pratos)}


@app.get("/cardapio/semana")
def cardapio_semana():
    return {"dias": get_cardapio_semana()}


@app.get("/chat/saudacao")
def saudacao():
    return {"mensagem": MENSAGEM_INICIAL}


@app.post("/chat", response_model=MensagemResponse)
def chat(request: MensagemRequest):
    try:
        resultado = processar_mensagem(request.session_id, request.mensagem)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {e}")

    return MensagemResponse(
        session_id=request.session_id,
        resposta=resultado["resposta"],
        fora_de_escopo=resultado["fora_de_escopo"],
    )


@app.delete("/chat/{session_id}")
def limpar(session_id: str):
    removido = resetar(session_id)
    return {"reset": removido}
