"""Robô de atualização das certidões do Grupo Carozzo.

Roda no GitHub Actions. Lê config/, consulta as fontes, guarda o último resultado de
cada certidão e grava tudo criptografado em docs/ para a tela ler.

Variáveis de ambiente (cadastradas como Secrets no GitHub):
  PAINEL_SENHA              obrigatória – mesma senha que a equipe digita na tela
  INFOSIMPLES_TOKEN         opcional – sem ele, as certidões pagas não são emitidas
  PORTAL_TRANSPARENCIA_KEY  opcional – chave gratuita para CEIS/CNEP sem custo
  FORCAR                    "true" para reemitir tudo, mesmo o que ainda está válido
"""
import csv
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from cripto import cifrar, decifrar  # noqa: E402

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS = os.path.join(RAIZ, "docs")
ARQ_DADOS = os.path.join(DOCS, "dados.enc")
PASTA_PDFS = os.path.join(DOCS, "pdfs")
FUSO = timezone(timedelta(hours=-3))
INFOSIMPLES_URL = "https://api.infosimples.com/api/v2/consultas/"

SENHA = os.environ.get("PAINEL_SENHA", "")
TOKEN = os.environ.get("INFOSIMPLES_TOKEN", "").strip()
CHAVE_TRANSP = os.environ.get("PORTAL_TRANSPARENCIA_KEY", "").strip()
FORCAR = os.environ.get("FORCAR", "").lower() in ("1", "true", "sim")

http = requests.Session()
http.headers["User-Agent"] = "controle-certidoes-carozzo/1.0"


# ---------------------------------------------------------------- utilidades
def hoje() -> date:
    return datetime.now(FUSO).date()


def agora_iso() -> str:
    return datetime.now(FUSO).isoformat(timespec="seconds")


def digitos(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def para_data(valor):
    """Converte os vários formatos de data das fontes para AAAA-MM-DD."""
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


def primeiro(d: dict, chaves, conv=None):
    for k in chaves:
        v = d.get(k)
        if v not in (None, "", []):
            return conv(v) if conv else v
    return None


def somar_dias(iso, dias):
    return (date.fromisoformat(iso) + timedelta(days=dias)).isoformat() if iso else None


# ---------------------------------------------------------------- leitura de dados
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
            chave = (cnpj, cid)
            emissao = para_data(r.get("emissao", ""))
            atual = linhas.get(chave)
            if atual is None or (emissao or "") >= (atual.get("emissao") or ""):
                r["emissao"] = emissao
                linhas[chave] = r
    return linhas


# ---------------------------------------------------------------- interpretação
def classificar(cert_id: str, d: dict) -> str:
    texto = json.dumps(
        {k: d.get(k) for k in ("mensagem", "certidao", "situacao", "descricao", "titulo", "observacoes")},
        ensure_ascii=False,
    ).upper()
    if "POSITIVA COM EFEITO" in texto:
        return "cpen"
    if cert_id == "crf_fgts":
        sit = str(d.get("situacao", "")).upper()
        if "IRREGULAR" in sit:
            return "positiva"
        if "REGULAR" in sit:
            return "negativa"
    if d.get("conseguiu_emitir_certidao_negativa") is True or d.get("nada_consta") is True:
        return "negativa"
    if d.get("consta") is True or d.get("nada_consta") is False or d.get("conseguiu_emitir_certidao_negativa") is False:
        return "positiva"
    total = primeiro(d, ["total_processos", "total_de_processos"])
    if isinstance(total, (int, float)):
        return "positiva" if total > 0 else "negativa"
    return "indefinido"


def contar_processos(d: dict):
    for k in ("total_processos", "total_de_processos"):
        if isinstance(d.get(k), (int, float)):
            return int(d[k])
    for k in ("processos", "processos_encontrados", "processos_encontrados_cpf_cnpj"):
        v = d.get(k)
        if isinstance(v, list):
            return len(v)
        if isinstance(v, dict):
            q = v.get("quantidade_processos")
            if isinstance(q, (int, float)):
                return int(q)
            if isinstance(v.get("lista_processos"), list):
                return len(v["lista_processos"])
    return None


CHAVES_VALIDADE = ["normalizado_validade", "validade_data", "data_validade", "validade_fim_data",
                   "data_hora_validade", "validade"]
CHAVES_EMISSAO = ["normalizado_emissao_datahora", "normalizado_data_hora_emissao", "emissao_data",
                  "datahora_emissao", "emissao_datahora", "data_hora_emissao", "normalizado_expedicao",
                  "expedicao", "datahora_expedicao", "horario_emissao", "data_criacao",
                  "validade_inicio_data", "consulta_datahora", "datahora"]
CHAVES_CODIGO = ["certidao_codigo", "codigo_controle", "codigo_validacao", "codigo_autenticidade",
                 "codigo_verificacao", "numero_certidao", "crf"]


# ---------------------------------------------------------------- fontes
def consultar_brasilapi(emp, cert):
    cnpj = digitos(emp["cnpj"])
    try:
        r = http.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=30)
        r.raise_for_status()
        j = r.json()
        sit = str(j.get("descricao_situacao_cadastral", "")).upper()
        nome = j.get("razao_social")
    except Exception:
        r = http.get(f"https://publica.cnpj.ws/cnpj/{cnpj}", timeout=30)
        r.raise_for_status()
        j = r.json()
        sit = str((j.get("estabelecimento") or {}).get("situacao_cadastral", "")).upper()
        nome = j.get("razao_social")
    return {
        "situacao": "negativa" if sit == "ATIVA" else "positiva",
        "emissao": hoje().isoformat(),
        "validade": somar_dias(hoje().isoformat(), 3),
        "mensagem": f"Situação cadastral: {sit or 'não informada'}" + (f" · Razão social na Receita: {nome}" if nome else ""),
        "tipo": "consulta",
    }


def consultar_transparencia(emp, cert):
    cnpj = digitos(emp["cnpj"])
    achados = []
    for base in ("ceis", "cnep"):
        r = http.get(
            f"https://api.portaldatransparencia.gov.br/api-de-dados/{base}",
            params={"codigoSancionado": cnpj, "pagina": 1},
            headers={"chave-api-dados": CHAVE_TRANSP, "accept": "application/json"},
            timeout=60,
        )
        r.raise_for_status()
        achados += [(base.upper(), x) for x in (r.json() or [])]
    return {
        "situacao": "positiva" if achados else "negativa",
        "emissao": hoje().isoformat(),
        "validade": somar_dias(hoje().isoformat(), 7),
        "mensagem": ("Sanções encontradas: " + ", ".join(sorted({b for b, _ in achados})))
        if achados else "Nada consta no CEIS e no CNEP (Portal da Transparência)",
        "tipo": "consulta",
    }


def consultar_infosimples(emp, cert, consumo):
    params = {"token": TOKEN, "timeout": 300, "cnpj": digitos(emp["cnpj"])}
    params.update(cert.get("parametros") or {})
    r = http.post(INFOSIMPLES_URL + cert["servico"], data=params, timeout=360)
    j = r.json()
    preco = (j.get("header") or {}).get("price")
    consumo["consultas"] = consumo.get("consultas", 0) + 1
    try:
        consumo["valor"] = round(consumo.get("valor", 0) + float(preco or 0), 2)
    except ValueError:
        pass
    if j.get("code") != 200:
        erros = "; ".join(j.get("errors") or []) or j.get("code_message") or "erro sem mensagem"
        raise RuntimeError(f"Infosimples {j.get('code')}: {erros}")
    d = (j.get("data") or [{}])[0]
    sit = classificar(cert["id"], d)
    emissao = primeiro(d, CHAVES_EMISSAO, para_data) or hoje().isoformat()
    validade = primeiro(d, CHAVES_VALIDADE, para_data)
    estimada = False
    if not validade and sit in ("negativa", "cpen"):
        validade, estimada = somar_dias(emissao, cert.get("validade_padrao_dias", 30)), True
    res = {
        "situacao": sit,
        "emissao": emissao,
        "validade": validade,
        "validade_estimada": estimada,
        "codigo": primeiro(d, CHAVES_CODIGO, str),
        "mensagem": primeiro(d, ["mensagem", "situacao", "descricao"], str),
        "processos": contar_processos(d),
        "tipo": "certidao",
    }
    recibos = j.get("site_receipts") or []
    if recibos:
        res["_recibo"] = recibos[0]
    return res


# ---------------------------------------------------------------- comprovantes (PDF)
def guardar_comprovante(url, nome_base, anterior):
    try:
        r = http.get(url, timeout=120)
        r.raise_for_status()
    except Exception:
        return anterior
    mime = "application/pdf" if r.content[:4] == b"%PDF" else (r.headers.get("content-type") or "text/html").split(";")[0]
    nome = f"{nome_base}_{hoje():%Y%m%d}.enc"
    os.makedirs(PASTA_PDFS, exist_ok=True)
    with open(os.path.join(PASTA_PDFS, nome), "w", encoding="utf-8") as f:
        f.write(cifrar(r.content, SENHA))
    if anterior and anterior.get("arquivo") != f"pdfs/{nome}":
        try:
            os.remove(os.path.join(DOCS, anterior["arquivo"]))
        except OSError:
            pass
    return {"arquivo": f"pdfs/{nome}", "mime": mime}


# ---------------------------------------------------------------- orquestração
def precisa_consultar(cert, anterior):
    if FORCAR or not anterior:
        return True
    if anterior.get("situacao") == "erro":
        # falha sem nenhum resultado bom: tenta de novo a cada 2 dias para não gerar custo diário
        ultima = para_data((anterior.get("ultima_falha") or {}).get("em", "")) or "2000-01-01"
        return (hoje() - date.fromisoformat(ultima)).days >= 2
    if not anterior.get("validade"):
        return True
    if cert.get("consulta_diaria"):
        return True
    if anterior.get("situacao") in ("positiva", "indefinido"):
        # pendência: reconsulta uma vez por semana para ver se regularizou
        ultima = para_data(anterior.get("consultado_em") or "") or "2000-01-01"
        return (hoje() - date.fromisoformat(ultima)).days >= 7
    restantes = (date.fromisoformat(anterior["validade"]) - hoje()).days
    return restantes <= cert.get("renovar_com_dias", 5)


def main():
    if not SENHA:
        sys.exit("Defina PAINEL_SENHA (Secret do repositório).")

    empresas = carregar_json("config/empresas.json")
    catalogo = carregar_json("config/certidoes.json")["certidoes"]
    estado = carregar_estado()
    resultados = estado.get("resultados", {})
    manuais = carregar_manuais()

    mes = hoje().strftime("%Y-%m")
    consumo = estado.get("consumo") if (estado.get("consumo") or {}).get("mes") == mes else {"mes": mes}
    resumo = {"consultadas": 0, "falhas": 0, "mantidas": 0, "sem_token": 0}

    emissores = {}  # raiz do CNPJ -> id da empresa que emite as certidões de escopo raiz
    for e in empresas:
        emissores.setdefault(digitos(e["cnpj"])[:8], e["id"])

    for cert in catalogo:
        for emp in empresas:
            if cert.get("aplica_a") and emp["id"] not in cert["aplica_a"]:
                continue
            chave = f"{emp['id']}|{cert['id']}"
            anterior = resultados.get(chave)

            if cert.get("escopo") == "raiz" and emissores[digitos(emp["cnpj"])[:8]] != emp["id"]:
                resultados[chave] = {"herdado_de": emissores[digitos(emp["cnpj"])[:8]]}
                continue

            if cert["fonte"] == "manual":
                m = manuais.get((digitos(emp["cnpj"]), cert["id"]))
                if not m:
                    resultados[chave] = {"situacao": "sem_registro", "tipo": "manual"}
                    continue
                res_txt = (m.get("resultado") or "").strip().lower()
                sit = {"negativa": "negativa", "regular": "negativa", "nada consta": "negativa",
                       "cpen": "cpen", "positiva com efeito de negativa": "cpen",
                       "positiva": "positiva", "com pendencia": "positiva", "com pendência": "positiva",
                       "nao aplicavel": "nao_aplicavel", "não aplicável": "nao_aplicavel"}.get(res_txt, "indefinido")
                validade = para_data(m.get("validade", ""))
                if not validade and m.get("emissao") and sit in ("negativa", "cpen"):
                    validade = somar_dias(m["emissao"], cert.get("validade_padrao_dias", 30))
                resultados[chave] = {
                    "situacao": sit, "emissao": m.get("emissao"), "validade": validade,
                    "mensagem": m.get("observacao") or None, "link_documento": m.get("link_documento") or None,
                    "tipo": "manual",
                }
                continue

            fonte = cert["fonte"]
            if cert.get("fonte_gratuita") == "transparencia" and CHAVE_TRANSP:
                fonte = "transparencia"
            if fonte == "infosimples" and not TOKEN:
                if not anterior or "situacao" not in anterior:
                    resultados[chave] = {"situacao": "nao_configurado", "tipo": "certidao"}
                resumo["sem_token"] += 1
                continue
            if not cert.get("ativo", True):
                continue
            if not precisa_consultar(cert, anterior if anterior and "situacao" in anterior else None):
                resumo["mantidas"] += 1
                continue

            try:
                if fonte == "brasilapi":
                    novo = consultar_brasilapi(emp, cert)
                elif fonte == "transparencia":
                    novo = consultar_transparencia(emp, cert)
                else:
                    novo = consultar_infosimples(emp, cert, consumo)
                recibo = novo.pop("_recibo", None)
                novo["comprovante"] = (
                    guardar_comprovante(recibo, chave.replace("|", "_"), (anterior or {}).get("comprovante"))
                    if recibo else None
                )
                novo["fonte"] = fonte
                novo["consultado_em"] = agora_iso()
                resultados[chave] = novo
                resumo["consultadas"] += 1
            except Exception as exc:  # mantém o último resultado bom e registra a falha
                base = anterior if anterior and "situacao" in anterior else {"situacao": "erro", "tipo": "certidao"}
                base["ultima_falha"] = {"em": agora_iso(), "mensagem": str(exc)[:300]}
                resultados[chave] = base
                resumo["falhas"] += 1

    novo_estado = {
        "versao": 1,
        "atualizado_em": agora_iso(),
        "empresas": empresas,
        "certidoes": catalogo,
        "resultados": resultados,
        "consumo": consumo,
        "ultima_execucao": resumo,
        "infosimples_configurado": bool(TOKEN),
    }
    os.makedirs(DOCS, exist_ok=True)
    with open(ARQ_DADOS, "w", encoding="utf-8") as f:
        f.write(cifrar(json.dumps(novo_estado, ensure_ascii=False).encode("utf-8"), SENHA))

    # O log do GitHub Actions pode ser público: só números, nada de resultado.
    print(f"Concluído: {resumo['consultadas']} consultas, {resumo['mantidas']} ainda válidas, "
          f"{resumo['falhas']} falhas, {resumo['sem_token']} aguardando token Infosimples.")


if __name__ == "__main__":
    main()
