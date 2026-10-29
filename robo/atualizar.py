"""Robô de atualização das certidões do Grupo Carozzo (modo gratuito).

Roda no GitHub Actions todo dia útil. Consulta sozinho, sem custo e sem login:
  - Receita Federal (base aberta do CNPJ): situação cadastral
  - TCU, consulta consolidada: licitantes inidôneos, CEIS, CNEP e improbidade (CNJ)
  - CAIXA: regularidade do FGTS (CRF), uma vez por semana ou perto do vencimento
  - PGFN: base aberta de devedores da dívida ativa, a cada novo trimestre
As demais certidões entram por dados/manuais.csv.

Tudo que vai para docs/ sai criptografado com a senha do painel.

Variáveis de ambiente (Secrets do repositório):
  PAINEL_SENHA   obrigatória – mesma senha que a equipe digita na tela
"""
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from cripto import cifrar, decifrar  # noqa: E402
import pgfn  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS = os.path.join(RAIZ, "docs")
ARQ_DADOS = os.path.join(DOCS, "dados.enc")
FUSO = timezone(timedelta(hours=-3))
SENHA = os.environ.get("PAINEL_SENHA", "")

http = requests.Session()
http.headers["User-Agent"] = "controle-certidoes-carozzo/2.0 (uso interno)"


def hoje() -> date:
    return datetime.now(FUSO).date()


def agora_iso() -> str:
    return datetime.now(FUSO).isoformat(timespec="seconds")


def digitos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def para_data(valor):
    if not valor or not isinstance(valor, str):
        return None
    v = valor.strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", v)
    if m:
        return f"{m[3]}-{m[2]}-{m[1]}"
    return None


def somar_dias(iso, dias):
    return (date.fromisoformat(iso) + timedelta(days=dias)).isoformat() if iso else None


def carregar_json(caminho):
    with open(os.path.join(RAIZ, caminho), encoding="utf-8") as f:
        return json.load(f)


def carregar_estado():
    if not os.path.exists(ARQ_DADOS):
        return {}
    try:
        with open(ARQ_DADOS, encoding="utf-8") as f:
            return json.loads(decifrar(f.read(), SENHA))
    except Exception:
        print("Aviso: não consegui abrir o estado anterior (senha trocada?). Começando do zero.")
        return {}


def carregar_manuais():
    caminho = os.path.join(RAIZ, "dados", "manuais.csv")
    linhas = {}
    if not os.path.exists(caminho):
        return linhas
    with open(caminho, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            cnpj, cid = digitos(r.get("cnpj", "")), (r.get("certidao_id") or "").strip()
            if not cnpj or not cid:
                continue
            r["emissao"] = para_data(r.get("emissao", ""))
            atual = linhas.get((cnpj, cid))
            if atual is None or (r["emissao"] or "") >= (atual.get("emissao") or ""):
                linhas[(cnpj, cid)] = r
    return linhas


def aplica(cert, emp):
    if cert.get("aplica_a") and emp["id"] not in cert["aplica_a"]:
        return False
    if cert.get("municipio") and cert["municipio"] != emp.get("municipio"):
        return False
    return True


# ---------------------------------------------------------------- fontes gratuitas
def consultar_receita(cnpj):
    """Base aberta do CNPJ. Tenta duas espelhadas públicas."""
    erros = []
    for url, ler in (
        (f"https://minhareceita.org/{cnpj}",
         lambda j: (j.get("descricao_situacao_cadastral"), j.get("data_situacao_cadastral"), j.get("razao_social"))),
        (f"https://publica.cnpj.ws/cnpj/{cnpj}",
         lambda j: ((j.get("estabelecimento") or {}).get("situacao_cadastral"),
                    (j.get("estabelecimento") or {}).get("data_situacao_cadastral"), j.get("razao_social"))),
    ):
        try:
            r = http.get(url, timeout=40)
            r.raise_for_status()
            sit, desde, nome = ler(r.json())
            sit = str(sit or "").upper()
            return {
                "situacao": "negativa" if sit == "ATIVA" else "positiva",
                "emissao": hoje().isoformat(),
                "validade": somar_dias(hoje().isoformat(), 4),
                "mensagem": f"Situação cadastral: {sit or 'não informada'}"
                            + (f" desde {para_data(desde) or desde}" if desde else "")
                            + (f" · {nome}" if nome else ""),
                "tipo": "consulta",
                "fonte": "Receita Federal (base aberta)",
            }
        except Exception as exc:
            erros.append(str(exc)[:120])
    raise RuntimeError(" | ".join(erros))


def consultar_tcu(cnpj):
    """Consulta consolidada do TCU: devolve um dicionário por cadastro."""
    url = f"https://certidoes-apf.apps.tcu.gov.br/api/rest/publico/certidoes/{cnpj}?seEmitirPDF=false"
    r = http.get(url, timeout=90)
    r.raise_for_status()
    j = r.json()
    saida = {}
    for c in j.get("certidoes") or []:
        texto = f"{c.get('emissor', '')} {c.get('tipo', '')} {c.get('descricao', '')}".upper()
        if "CNIA" in texto or "IMPROBIDADE" in texto or c.get("emissor") == "CNJ":
            chave = "cnj"
        elif "CNEP" in texto or "PUNIDAS" in texto:
            chave = "cnep"
        elif "CEIS" in texto or "SUSPENSAS" in texto:
            chave = "ceis"
        elif "INIDÔNEO" in texto or "INIDONEO" in texto:
            chave = "tcu"
        else:
            continue
        sit = str(c.get("situacao", "")).upper()
        emissao = para_data(c.get("dataHoraEmissao", "")) or hoje().isoformat()
        if sit == "NADA_CONSTA":
            s = "negativa"
        elif sit in ("CONSTA", "NADA_CONSTA_COM_RESSALVA") or sit.startswith("CONSTA"):
            s = "positiva"
        else:
            raise_msg = {"SISTEMA_INDISPONIVEL": "Sistema do órgão indisponível na hora da consulta"}.get(sit, sit)
            saida[chave] = {"erro": raise_msg, "link": c.get("linkConsultaManual")}
            continue
        saida[chave] = {
            "situacao": s,
            "emissao": emissao,
            "validade": somar_dias(emissao, 4),
            "mensagem": f"{c.get('descricao', '')}: {'Nada consta' if s == 'negativa' else 'Consta registro'}",
            "tipo": "consulta",
            "fonte": f"TCU – consulta consolidada ({c.get('emissor', '')})",
            "link_documento": c.get("linkConsultaManual"),
        }
    return saida


# ---------------------------------------------------------------- orquestração
def manual_para_resultado(m, cert):
    res_txt = (m.get("resultado") or "").strip().lower()
    sit = {"negativa": "negativa", "regular": "negativa", "nada consta": "negativa",
           "cpen": "cpen", "positiva com efeito de negativa": "cpen",
           "positiva": "positiva", "com pendencia": "positiva", "com pendência": "positiva",
           "nao aplicavel": "nao_aplicavel", "não aplicável": "nao_aplicavel"}.get(res_txt, "indefinido")
    validade = para_data(m.get("validade", ""))
    if not validade and m.get("emissao") and sit in ("negativa", "cpen"):
        validade = somar_dias(m["emissao"], cert.get("validade_padrao_dias", 30))
    return {"situacao": sit, "emissao": m.get("emissao"), "validade": validade,
            "mensagem": m.get("observacao") or None, "link_documento": m.get("link_documento") or None,
            "tipo": "manual"}


def fgts_precisa(anterior):
    if not anterior or anterior.get("situacao") in (None, "erro", "positiva"):
        ultima = para_data((anterior or {}).get("consultado_em", "")) or "2000-01-01"
        return (hoje() - date.fromisoformat(ultima)).days >= 1
    ultima = para_data(anterior.get("consultado_em", "")) or "2000-01-01"
    if (hoje() - date.fromisoformat(ultima)).days >= 7:
        return True
    v = anterior.get("validade")
    return bool(v) and (date.fromisoformat(v) - hoje()).days <= 5


def main():
    if not SENHA:
        sys.exit("Defina PAINEL_SENHA (Secret do repositório).")

    empresas = carregar_json("config/empresas.json")
    catalogo = carregar_json("config/certidoes.json")["certidoes"]
    estado_ant = carregar_estado()
    anteriores = estado_ant.get("resultados", {})
    pgfn_info = estado_ant.get("pgfn") or {}
    manuais = carregar_manuais()
    resultados = {}
    resumo = {"consultadas": 0, "falhas": 0}

    emissores = {}
    for e in empresas:
        emissores.setdefault(digitos(e["cnpj"])[:8], e["id"])

    tcu_cache, receita_cache = {}, {}
    fgts_cli = None

    # PGFN: baixa a base só quando sai um trimestre novo
    raizes = sorted({digitos(e["cnpj"])[:8] for e in empresas})
    try:
        tri = pgfn.ultimo_trimestre(http, hoje())
        if tri != pgfn_info.get("trimestre") or set(raizes) - set(pgfn_info.get("raizes", {})):
            print(f"PGFN: lendo a base {tri} (pode levar alguns minutos)")
            achados = pgfn.buscar(http, tri, raizes)
            pgfn_info = {"trimestre": tri, "consultado_em": agora_iso(),
                         "raizes": {r: pgfn.resumo(achados[r], tri) for r in raizes}}
    except Exception as exc:
        print("PGFN: falha ao ler a base")
        pgfn_info = dict(pgfn_info, falha=str(exc)[:300])

    for cert in catalogo:
        for emp in empresas:
            if not aplica(cert, emp):
                continue
            chave = f"{emp['id']}|{cert['id']}"
            anterior = anteriores.get(chave) or {}
            raiz = digitos(emp["cnpj"])[:8]

            if cert.get("escopo") == "raiz" and emissores[raiz] != emp["id"]:
                resultados[chave] = {"herdado_de": emissores[raiz]}
                continue

            if cert["fonte"] == "manual":
                m = manuais.get((digitos(emp["cnpj"]), cert["id"]))
                resultados[chave] = manual_para_resultado(m, cert) if m else {"situacao": "sem_registro", "tipo": "manual"}
                continue

            cnpj = digitos(emp["cnpj"])
            try:
                if cert["fonte"] == "fgts":
                    if not fgts_precisa(anterior):
                        resultados[chave] = anterior
                        continue
                    if fgts_cli is None:
                        import fgts
                        fgts_cli = fgts.ConsultaFGTS()
                    novo = fgts_cli.consultar(cnpj)
                    time.sleep(2)
                elif cert["fonte"] == "pgfn":
                    item = (pgfn_info.get("raizes") or {}).get(cnpj[:8])
                    if not item:
                        raise RuntimeError(pgfn_info.get("falha") or "Base da PGFN ainda não lida")
                    emissao = para_data(pgfn_info.get("consultado_em", "")) or hoje().isoformat()
                    novo = dict(item, emissao=emissao, validade=somar_dias(emissao, 100), tipo="consulta",
                                fonte=f"PGFN – dados abertos ({pgfn_info.get('trimestre')})",
                                link_documento="https://www.gov.br/pgfn/pt-br/assuntos/divida-ativa-da-uniao/transparencia-fiscal-1/dados-abertos")
                    novo["consultado_em"] = pgfn_info.get("consultado_em") or agora_iso()
                    resultados[chave] = novo
                    resumo["consultadas"] += 1
                    continue
                elif cert["fonte"] == "receita":
                    if cnpj not in receita_cache:
                        receita_cache[cnpj] = consultar_receita(cnpj)
                    novo = dict(receita_cache[cnpj])
                else:
                    if cnpj not in tcu_cache:
                        tcu_cache[cnpj] = consultar_tcu(cnpj)
                        time.sleep(1)
                    item = tcu_cache[cnpj].get(cert["tcu_chave"])
                    if not item:
                        raise RuntimeError("Cadastro não veio na resposta do TCU")
                    if "erro" in item:
                        raise RuntimeError(item["erro"])
                    novo = dict(item)
                novo["consultado_em"] = agora_iso()
                resultados[chave] = novo
                resumo["consultadas"] += 1
            except Exception as exc:
                base = {k: v for k, v in anterior.items() if k != "ultima_falha"} if anterior.get("situacao") not in (None, "erro") else {"situacao": "erro", "tipo": "consulta"}
                base["ultima_falha"] = {"em": agora_iso(), "mensagem": str(exc)[:300]}
                resultados[chave] = base
                resumo["falhas"] += 1

    if fgts_cli is not None:
        fgts_cli.fechar()

    estado = {
        "pgfn": pgfn_info,
        "versao": 2,
        "modo": "gratuito",
        "atualizado_em": agora_iso(),
        "empresas": empresas,
        "certidoes": catalogo,
        "resultados": resultados,
        "ultima_execucao": resumo,
    }
    os.makedirs(DOCS, exist_ok=True)
    with open(ARQ_DADOS, "w", encoding="utf-8") as f:
        f.write(cifrar(json.dumps(estado, ensure_ascii=False).encode("utf-8"), SENHA))
    print(f"Concluído: {resumo['consultadas']} consultas automáticas, {resumo['falhas']} falhas.")


if __name__ == "__main__":
    main()
