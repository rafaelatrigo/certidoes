"""Dívida ativa da União pela base aberta da PGFN.

A PGFN publica, a cada trimestre, três arquivos com todos os devedores inscritos:
  - Dados_abertos_Sistema_SIDA.zip   (dívida ativa geral, não previdenciária)
  - Dados_abertos_Previdenciario.zip (dívida previdenciária)
  - Dados_abertos_FGTS.zip           (FGTS inscrito em dívida ativa)

O robô baixa os três, procura a raiz dos CNPJs do grupo e devolve, por raiz,
quantas inscrições existem, em que situação e o valor consolidado.
Os arquivos são grandes: só são baixados quando sai um trimestre novo.
"""
import csv
import io
import os
import re
import tempfile
import zipfile
from datetime import date

import requests

BASE = "https://dadosabertos.pgfn.gov.br"
ARQUIVOS = {
    "Geral (SIDA)": "Dados_abertos_Sistema_SIDA.zip",
    "Previdenciária": "Dados_abertos_Previdenciario.zip",
    "FGTS": "Dados_abertos_FGTS.zip",
}


def trimestres_recentes(hoje: date, quantos=4):
    a, t = hoje.year, (hoje.month - 1) // 3 + 1
    for _ in range(quantos):
        t -= 1
        if t == 0:
            a, t = a - 1, 4
        yield f"{a}_trimestre_{t:02d}"


def ultimo_trimestre(http, hoje: date):
    for tri in [f"{hoje.year}_trimestre_{(hoje.month - 1) // 3 + 1:02d}", *trimestres_recentes(hoje)]:
        url = f"{BASE}/{tri}/{ARQUIVOS['FGTS']}"
        try:
            r = http.head(url, timeout=30, allow_redirects=True)
            if r.status_code == 200:
                return tri
        except requests.RequestException:
            pass
    raise RuntimeError("Não encontrei a base trimestral da PGFN")


def _numero(v):
    v = (v or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def buscar(http, trimestre, raizes):
    """Devolve {raiz: [ {base, situacao, valor, ajuizado} ...]} para as raízes pedidas."""
    achados = {r: [] for r in raizes}
    for nome_base, arquivo in ARQUIVOS.items():
        url = f"{BASE}/{trimestre}/{arquivo}"
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, arquivo)
            with http.get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(caminho, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
            with zipfile.ZipFile(caminho) as z:
                for membro in z.namelist():
                    if not membro.lower().endswith((".csv", ".txt")):
                        continue
                    with z.open(membro) as bruto:
                        leitor = csv.reader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")
                        cab = [c.strip().upper() for c in next(leitor, [])]
                        i_doc = cab.index("CPF_CNPJ") if "CPF_CNPJ" in cab else 0
                        i_sit = cab.index("SITUACAO_INSCRICAO") if "SITUACAO_INSCRICAO" in cab else None
                        i_val = cab.index("VALOR_CONSOLIDADO") if "VALOR_CONSOLIDADO" in cab else None
                        i_ajz = cab.index("INDICADOR_AJUIZADO") if "INDICADOR_AJUIZADO" in cab else None
                        for linha in leitor:
                            if len(linha) <= i_doc:
                                continue
                            doc = re.sub(r"\D", "", linha[i_doc])
                            if len(doc) != 14 or doc[:8] not in achados:
                                continue
                            achados[doc[:8]].append({
                                "base": nome_base,
                                "situacao": linha[i_sit].strip() if i_sit is not None else "",
                                "valor": _numero(linha[i_val]) if i_val is not None else 0.0,
                                "ajuizado": (linha[i_ajz].strip().upper() == "SIM") if i_ajz is not None else False,
                            })
    return achados


def resumo(lista, trimestre):
    ano, tri = trimestre.split("_trimestre_")
    t = f"{int(tri)}º trimestre de {ano}"
    if not lista:
        return {"situacao": "negativa", "mensagem": f"Nada consta na base aberta da PGFN ({t})"}
    total = sum(x["valor"] for x in lista)
    bases = sorted({x["base"] for x in lista})
    ajuizadas = sum(1 for x in lista if x["ajuizado"])
    valor = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return {
        "situacao": "positiva",
        "mensagem": f"{len(lista)} inscrição(ões) em dívida ativa ({', '.join(bases)}), total {valor}"
                    + (f", {ajuizadas} ajuizada(s)" if ajuizadas else "") + f" · base PGFN {t}",
    }
