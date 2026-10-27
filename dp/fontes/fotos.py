"""Fotos oficiais dos parlamentares (Câmara e Senado), em cache local.

Cada arquivo leva a origem gravada no próprio JPEG (segmento de comentário),
para que a procedência da imagem viaje com ela.
"""
import shutil
import subprocess
from pathlib import Path

from dp import config, http

PASTA = config.DATA_DIR / "fotos"
LARGURA = 360
CHAVE_ORIGEM = "impeccable:prompt"

URL_FOTO = {
    "camara": "https://www.camara.leg.br/internet/deputado/bandep/{id}.jpg",
    "senado": "https://legis.senado.leg.br/senadores/fotos-oficiais/{id}",
}


def caminho(parlamentar_id: str) -> Path:
    return PASTA / (parlamentar_id.replace(":", "_") + ".jpg")


def gravar_origem(jpeg: bytes, texto: str) -> bytes:
    """Insere um segmento COM logo após o SOI com a origem da imagem."""
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("não é JPEG")
    seg = f"{CHAVE_ORIGEM}\0{texto}".encode("utf-8")
    com = b"\xff\xfe" + (len(seg) + 2).to_bytes(2, "big") + seg
    return jpeg[:2] + com + jpeg[2:]


def _reduzir(arquivo: Path):
    """Reduz para LARGURA px com o `sips` do macOS, se existir; senão mantém."""
    if shutil.which("sips"):
        subprocess.run(["sips", "--resampleWidth", str(LARGURA), "-s", "formatOptions", "70",
                        str(arquivo)], check=True, capture_output=True)


def baixar(parlamentar_id: str, refazer: bool = False) -> Path:
    destino = caminho(parlamentar_id)
    if destino.exists() and not refazer:
        return destino
    casa, id_externo = parlamentar_id.split(":", 1)
    url = URL_FOTO[casa].format(id=id_externo)
    conteudo = http.get(url, accept="image/jpeg", pausa=0.2).content
    PASTA.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    _reduzir(destino)
    origem = f"Foto oficial publicada por {'Câmara dos Deputados' if casa == 'camara' else 'Senado Federal'}: {url}"
    destino.write_bytes(gravar_origem(destino.read_bytes(), origem))
    return destino
