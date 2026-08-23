from pydantic import BaseModel, Field


class Turno(BaseModel):
    papel: str
    conteudo: str


class InferRequest(BaseModel):
    session_id: str = Field(default="", max_length=128)
    unidade_id: int
    usuario_id: int | None = None
    mensagem: str = Field(..., min_length=1, max_length=2000)
    historico: list[Turno] = Field(default_factory=list)


class Confianca(BaseModel):
    """Sinal de incerteza do turno. Ausente quando tudo foi reconhecido."""

    nivel: str
    nao_reconhecidos: list[str] = Field(default_factory=list)


class InferResponse(BaseModel):
    resposta: str
    fora_de_escopo: bool = False
    confianca: Confianca | None = None
