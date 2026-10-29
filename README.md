# Certidões Carozzo

Painel interno com a situação das certidões das empresas e SPEs do Grupo Carozzo, publicado no GitHub Pages e protegido por senha. Funciona **sem nenhum sistema pago**.

## Como funciona

Um robô (GitHub Actions) roda todo dia útil às 06:17 e consulta sozinho, de graça e sem login:

| Consulta | Fonte |
|---|---|
| Situação cadastral do CNPJ | Receita Federal, base aberta (minhareceita.org, com reserva em publica.cnpj.ws) |
| Licitantes inidôneos | TCU, consulta consolidada (API pública) |
| CEIS e CNEP | Portal da Transparência, pela consulta do TCU |
| Improbidade (CNIA) | CNJ, pela consulta do TCU (o sistema do CNJ cai com frequência) |
| Regularidade do FGTS (CRF) | CAIXA, formulário público sem captcha; toda semana e perto do vencimento |
| Dívida ativa da União | PGFN, base aberta trimestral (geral, previdenciária e FGTS); indica dívida inscrita, não substitui a CND |

As demais certidões (CND Federal, CNDT, estadual, municipais, TJBA, TRF1, cartórios etc.) entram por lançamento manual. A aba **O que a IA consegue fazer** mostra, para cada uma, o custo, o acesso exigido, o que impede a automação e como emitir.

Tudo que fica em `docs/` é criptografado com a senha do painel (AES-256-GCM). O log do robô mostra só contagens.

## Estrutura

```
config/empresas.json     CNPJs monitorados (inclua ou retire aqui)
config/certidoes.json    catálogo: fonte, custo, acesso, motivo, como fazer, link
dados/manuais.csv        lançamento das certidões emitidas à mão
docs/index.html          a tela
docs/marca/              logo da Carozzo (logo-carozzo.png)
docs/dados.enc           dados criptografados (gerado pelo robô)
robo/                    robô de consulta e criptografia
.github/workflows/       agenda do robô
```

## Configuração no GitHub (uma vez)

1. **Senha**: Settings → Secrets and variables → Actions → `PAINEL_SENHA`.
2. **Permissão do robô**: Settings → Actions → General → Workflow permissions → **Read and write permissions**.
3. **Publicar a tela**: Settings → Pages → Deploy from a branch → `main` / `/docs`.
4. **Logo**: envie o logo para `docs/marca/logo-carozzo.png` (Add file → Upload files). Sem o arquivo, a tela mostra o nome CAROZZO por extenso.
5. **Primeira carga**: Actions → Atualizar certidões → Run workflow.

Endereço: `https://rafaelatrigo.github.io/certidoes/`

Os Secrets `INFOSIMPLES_TOKEN` e `PORTAL_TRANSPARENCIA_KEY` não são mais usados e podem ser apagados.

## Lançar uma certidão manual

Edite `dados/manuais.csv` no próprio GitHub (lápis ✏️) e salve. A tela atualiza em 1 a 2 minutos.

```
cnpj;certidao_id;resultado;emissao;validade;observacao;link_documento
21.049.800/0001-77;cnd_federal;negativa;29/10/2026;27/04/2027;;https://...sharepoint.../CND.pdf
```

- `resultado`: `negativa`, `cpen`, `positiva` ou `nao aplicavel`.
- Validade vazia: o robô usa o prazo padrão da certidão.
- Os ids estão em `config/certidoes.json` (`cnd_federal`, `crf_fgts`, `cndt`, `ceat_trt5`, `cnd_estadual`, `cnd_salvador`, `cnd_feira`, `tjba`, `trf1`, `protesto` etc.).
- Certidões de raiz (Federal, CNDT, TRF1, Salvador, protesto) são lançadas só no CNPJ da matriz e valem para as filiais.

## Cores da marca

As cores ficam no topo de `docs/index.html`, no bloco `MARCA CAROZZO` (`--marca-grafite`, `--marca-pedra`, `--marca-areia`). Para usar exatamente as mesmas do painel de despesas, copie os valores de lá.
