from pydantic import BaseModel, Field


class MensagemRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    mensagem: str = Field(..., min_length=1, max_length=2000)


class MensagemResponse(BaseModel):
    session_id: str
    resposta: str
    fora_de_escopo: bool = False
