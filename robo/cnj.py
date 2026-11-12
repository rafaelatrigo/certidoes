"""Consulta direta ao CNIA do CNJ (Cadastro Nacional de Condenações por Improbidade).

Abre o formulário público num navegador sem tela, pesquisa o CNPJ (pessoa jurídica,
todas as esferas) e baixa a certidão oficial em PDF que o próprio site gera.
O formulário não tem captcha; se um dia passar a ter, a consulta para e devolve erro.
"""
import re

BASE = "https://www.cnj.jus.br/improbidade_adm/"
URL = BASE + "consultar_requerido.php"


class ConsultaCNJ:
    def __init__(self):
        import navegador
        self._ctx = navegador.browser().new_context(
            locale="pt-BR", timezone_id="America/Sao_Paulo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        self._page = self._ctx.new_page()
        self._page.set_default_timeout(40000)

    def fechar(self):
        try:
            self._ctx.close()
        except Exception:
            pass

    def consultar(self, cnpj_digitos):
        p = self._page
        try:
            resp = p.goto(URL, wait_until="domcontentloaded", timeout=60000)
            p.wait_for_selector("#num_cpf_cnpj", state="visible", timeout=30000)
        except Exception as exc:
            raise RuntimeError(f"Site do CNJ não respondeu ao robô: {str(exc).splitlines()[0][:120]}")
        if p.locator("iframe[src*='captcha'], img[src*='captcha'], [id*='captcha']").count():
            raise RuntimeError("O CNJ passou a exigir captcha; consulta não automatizável")

        p.check("#tipoPessoaJuridica")
        p.fill("#num_cpf_cnpj", cnpj_digitos)
        p.click("input[value='Pesquisar']")
        # o site mostra "Pesquisando..." e só depois envia o formulário: espera a tabela de resultado
        texto = ""
        for _ in range(60):
            p.wait_for_timeout(1000)
            try:
                texto = " ".join(p.inner_text("body").split())
            except Exception:
                continue   # página trocando no meio da leitura
            if "Nenhum Requerido encontrado" in texto or re.search(r"N[úu]m\. Processo", texto):
                break

        if "Nenhum Requerido encontrado" in texto:
            situacao, tipo_cert = "negativa", "N"
            msg = "CNIA/CNJ: nenhuma condenação por improbidade"
        elif re.search(r"N[úu]m\. Processo", texto):
            situacao, tipo_cert = "positiva", "P"
            msg = "CNIA/CNJ: há registro de condenação por improbidade. Verificar com o jurídico"
        else:
            raise RuntimeError("Resposta do CNJ não reconhecida: " + texto[-160:])

        pdf = None
        try:
            r = p.request.get(f"{BASE}certidao.php?tipoCertidao={tipo_cert}&cpfCnpj={cnpj_digitos}&tipoPessoa=J", timeout=40000)
            corpo = r.body()
            if r.ok and corpo[:5] == b"%PDF-":
                pdf = corpo
        except Exception:
            pdf = None

        return {
            "situacao": situacao,
            "mensagem": msg,
            "tipo": "consulta",
            "fonte": "CNJ – CNIA (consulta pública)",
            "link_documento": URL,
            "_pdf": pdf,
        }
