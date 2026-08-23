"""Chunking do RAG: janelas, quebra em separador e overlap."""

from app.rag.chunking import chunk


def test_texto_curto_vira_um_chunk():
    assert chunk("guia curto") == ["guia curto"]


def test_texto_vazio_vira_lista_vazia():
    assert chunk("") == []
    assert chunk("   ") == []


def test_quebra_prefere_paragrafo():
    texto = ("A" * 500) + "\n\n" + ("B" * 500)
    pedacos = chunk(texto, tamanho=800, overlap=100)
    assert len(pedacos) >= 2
    # o primeiro pedaço termina no limite do parágrafo, não no meio dos B's
    assert pedacos[0].rstrip() == "A" * 500


def test_todo_conteudo_e_coberto():
    palavras = " ".join(f"palavra{i}" for i in range(400))
    pedacos = chunk(palavras, tamanho=800, overlap=100)
    reconstruido = " ".join(pedacos)
    for i in range(400):
        assert f"palavra{i}" in reconstruido


def test_overlap_repete_final_do_pedaco_anterior():
    palavras = " ".join(f"p{i:03d}" for i in range(300))
    pedacos = chunk(palavras, tamanho=400, overlap=80)
    assert len(pedacos) >= 2
    # o início do 2º pedaço deve reaparecer no fim do 1º (janela sobreposta)
    inicio_do_segundo = pedacos[1][:20].strip().split()[0]
    assert inicio_do_segundo in pedacos[0]
