# Certidões Carozzo

Painel com a situação das certidões das empresas e SPEs do Grupo Carozzo. Um robô no GitHub Actions emite e consulta as certidões sozinho, e a tela (GitHub Pages, protegida por senha) mostra o que está regular, a vencer, vencido ou com pendência.

## O que sai sozinho

| Certidão | Fonte | Custo |
|---|---|---|
| Situação cadastral do CNPJ | BrasilAPI | grátis, todo dia útil |
| CND Federal (RFB/PGFN) | Infosimples | pago |
| CRF – FGTS | Infosimples | pago |
| CND Estadual (SEFAZ-BA) | Infosimples | pago |
| CNDT (TST) | Infosimples | pago |
| CEAT (TRT5) | Infosimples | pago |
| Distribuição cível e falência (TJBA) | Infosimples | pago |
| Distribuição cível federal (TRF1) | Infosimples | pago |
| Correcional CGU (CEIS/CNEP/CEPIM) | Portal da Transparência ou Infosimples | grátis com a chave do Portal |

O robô só reemite quando a certidão está perto de vencer (prazo em `renovar_com_dias` no `config/certidoes.json`). Certidões de escopo "raiz" (CND Federal, CNDT, TRF1, municipal, protesto) são emitidas uma vez pela matriz e valem para as filiais.

Estimativa: cerca de 60 a 80 consultas pagas por mês para os 8 CNPJs, a partir de R$ 0,20 cada. A franquia mínima da Infosimples é R$ 100/mês, então o custo esperado fica nesse patamar. A conta nova vem com R$ 100 de crédito para teste.

## O que continua manual

Sem API confiável: CND municipal de Salvador, protesto (CENPROT), birôs (Serasa, SPC, Boa Vista, Quod), CADIN, JUCEB, CND de obra/CNO, matrícula e ônus, ações reais, IPTU, SPU (Porto) e licenças.

Para lançar: edite `dados/manuais.csv` no próprio GitHub (lápis ✏️ no arquivo) e salve. A tela atualiza sozinha em 1 a 2 minutos.

```
cnpj;certidao_id;resultado;emissao;validade;observacao;link_documento
37.152.367/0001-30;spu;cpen;01/08/2026;30/10/2026;Foro 2026 parcelado;https://...sharepoint.../CAT.pdf
```

`resultado` aceita: `negativa`, `cpen`, `positiva`, `nao aplicavel`. Se a validade ficar vazia, o robô usa o prazo padrão da certidão. Os ids de certidão estão em `config/certidoes.json`.

## Instalação (uma vez)

1. Crie um repositório novo no GitHub (ex.: `certidoes`) e envie todos estes arquivos.
2. **Settings → Secrets and variables → Actions → New repository secret**:
   - `PAINEL_SENHA`: a senha que a equipe vai digitar na tela.
   - `INFOSIMPLES_TOKEN`: token criado em api.infosimples.com (Área do Cliente → Tokens).
   - `PORTAL_TRANSPARENCIA_KEY` (opcional): chave gratuita em portaldatransparencia.gov.br/api-de-dados/cadastrar-email.
3. **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main`, pasta `/docs`.
4. **Actions → Atualizar certidões → Run workflow** para a primeira carga.
5. Abra o endereço do GitHub Pages e entre com a senha.

Depois disso o robô roda todo dia útil às 06:17 (Brasília). Para reemitir tudo na hora, use **Run workflow** marcando "Reemitir tudo".

## Segurança

O repositório pode ser público: tudo que fica em `docs/` (dados e comprovantes em PDF) é criptografado com a senha do painel (AES-256-GCM, chave derivada por PBKDF2). O log do Actions mostra só contagens. Se trocar a senha, rode o workflow com "Reemitir tudo".

## Primeira execução: o que conferir

- **TJBA**: o valor do parâmetro `tipo_certidao` (`civel`, `falencia`) precisa ser confirmado na documentação da Infosimples. Se vier errado, a célula aparece como "Falha na consulta" com a mensagem do erro; ajuste em `config/certidoes.json`.
- **CNPJ da filial do Terrazza Balena**: cadastrado como `47.537.136/0002-80`. A lista original trazia `0002-88`, que não fecha no dígito verificador.
- **Ícone**: só a filial `54.338.722/0002-60` está cadastrada. Se a matriz também precisar ser acompanhada, inclua-a em `config/empresas.json`.
