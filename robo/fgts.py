"""Consulta de regularidade do FGTS (CRF) no site público da CAIXA.

Abre o formulário num navegador sem tela (Playwright), informa o CNPJ e lê:
  - se a empresa está REGULAR ou não
  - a validade e o número do Certificado de Regularidade (CRF)

Não há captcha nesse formulário. Se um dia a CAIXA passar a exigir captcha,
a consulta para e devolve erro: o robô não tenta contorná-lo.
"""
import re

URL = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"


def _data_iso(txt):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt or "")
    return f"{m[3]}-{m[2]}-{m[1]}" if m else None


class ConsultaFGTS:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(locale="pt-BR")
        self._page.set_default_timeout(45000)

    def fechar(self):
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def consultar(self, cnpj_digitos):
        p = self._page
        p.goto(URL, wait_until="domcontentloaded")
        texto_inicial = p.inner_text("body").lower()
        if "captcha" in texto_inicial or p.locator("iframe[src*='captcha'], img[src*='captcha']").count():
            raise RuntimeError("A CAIXA passou a exigir captcha; consulta não automatizável")

        campo = p.locator("input[type='text']:visible").first
        campo.fill(cnpj_digitos)
        p.get_by_role("button", name=re.compile("Consultar", re.I)).click()
        p.wait_for_load_state("networkidle")
        texto = p.inner_text("body")
        t = texto.upper()

        if "REGULAR NO FGTS" in t and "IRREGULAR" not in t:
            situacao = "negativa"
        elif "IRREGULAR" in t or "NÃO FOI POSSÍVEL" in t or "NAO FOI POSSIVEL" in t:
            situacao = "positiva"
        else:
            raise RuntimeError("Resposta da CAIXA não reconhecida: " + " ".join(texto.split())[:160])

        validade = emissao = numero = None
        if situacao == "negativa":
            link = p.get_by_text(re.compile("Certificado de Regularidade do FGTS", re.I)).first
            if link.count():
                link.click()
                p.wait_for_load_state("networkidle")
                crf = p.inner_text("body")
                m = re.search(r"Validade:\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})", crf)
                if m:
                    emissao, validade = _data_iso(m[1]), _data_iso(m[2])
                m = re.search(r"Certificado N[úu]mero:\s*(\d+)", crf)
                numero = m[1] if m else None

        msg = "Regular no FGTS" if situacao == "negativa" else "Não está regular no FGTS (ver site da CAIXA)"
        if numero:
            msg += f" · CRF nº {numero}"
        return {
            "situacao": situacao,
            "emissao": emissao,
            "validade": validade,
            "mensagem": msg,
            "tipo": "certidao" if validade else "consulta",
            "fonte": "CAIXA – consulta pública de regularidade do FGTS",
            "link_documento": URL,
        }
