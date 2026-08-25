# Verllog — onde o projeto está

Última atualização: 25/08/2026

Resumo do que já foi feito, das decisões tomadas e do que falta. Serve para
retomar o trabalho depois de um tempo sem mexer.

---

## Endereços e acessos

| O quê | Onde |
|---|---|
| Site | https://verllog.onrender.com |
| Painel | https://verllog.onrender.com/admin |
| Código | https://github.com/polvomal07/verllog |
| Hospedagem | Render, serviço `verllog` |
| Banco | Neon, projeto Verllog, região AWS São Paulo |
| Pasta local | `C:\Users\PICHAU\Documents\transportadora` |

Usuário do painel: `admin`. A senha fica no Render, em **Settings →
Environment → ADMIN_SENHA**, e pode ser trocada por lá a qualquer momento.

---

## Como funciona

```
planilha CSV/XLSX
      ↓  upload em /admin
  importador (pandas)
      ↓  valida, deduplica pelo código de rastreio
  PostgreSQL no Neon
      ↓  motor de rotas monta o trajeto por cidade/UF
  site público: mostra só o que já aconteceu
```

**O status não é gravado.** Cada pedido tem as movimentações no banco com data
e hora definitivas; o site mostra as que já passaram. Nenhum processo roda em
segundo plano, e o computador pode ficar desligado por semanas.

---

## Regras em vigor

| Regra | Valor | Onde muda |
|---|---|---|
| Código de rastreio | 2 letras + 12 números + 1 letra | `config.py` → `CODIGO_REGEX` |
| Códigos antigos fora do padrão | aceitos | `config.py` → `ACEITAR_CODIGOS_LEGADOS` |
| Origem de todas as rotas | Manaus/AM | `services/rotas.py` → `CENTRO_MATRIZ` |
| Duração do ciclo | 35 dias | `config.py` → `CRONOGRAMA` |
| Tentativa frustrada | dia 28 | `config.py` → `CRONOGRAMA` |
| Nova tentativa | dia 30 | `config.py` → `CRONOGRAMA` |
| Cliente vê | só o que já aconteceu | `services/rastreamento.py` |
| Previsão de entrega | oculta no site, visível no painel | `templates/rastreamento.html` |

Mexeu em alguma dessas? Rode `python -m flask regravar-rotas` para recalcular
os pedidos existentes.

---

## Cronograma da entrega

```
dia  0   Pedido recebido                      Manaus/AM
dia  3   Pedido processado                    Manaus/AM
dia  6   Objeto coletado                      Manaus/AM
dia 6-20 Em transferência                     centros no caminho
dia 20   Centro de distribuição               cidade destino
dia 24   Unidade de destino                   cidade destino
dia 28   Tentativa de entrega não realizada   cidade destino
dia 30   Nova tentativa de entrega            cidade destino
dia 33   Saiu para entrega                    cidade destino
dia 35   Entregue                             cidade destino
```

As transferências são o único trecho elástico: quantas houver, elas se
distribuem entre os dias 6 e 20, e o total continua fechando em 35 dias.

---

## Comandos

Antes de qualquer um:

```powershell
cd C:\Users\PICHAU\Documents\transportadora
.\.venv\Scripts\Activate.ps1
$env:FLASK_APP = "app.py"
```

| Comando | O que faz |
|---|---|
| `python app.py` | sobe o site local em http://127.0.0.1:5000 |
| `python -m flask conferir ARQUIVO` | analisa a planilha sem gravar nada |
| `python -m flask importar ARQUIVO` | importa a planilha |
| `python -m flask listar` | lista os pedidos com o status de hoje |
| `python -m flask rastrear CODIGO` | mostra a timeline no terminal |
| `python -m flask regravar-rotas` | recalcula trajetos preservando as datas |
| `python -m flask espalhar-datas --ate 40` | espalha as datas (só para demonstração) |
| `python -m flask iniciar-banco --zerar` | apaga tudo e recria as tabelas |

Scripts auxiliares em `scripts/`: geração de planilha de teste, planilhas com
defeito, teste do motor, teste de reimportação e medição de armazenamento.

---

## Publicar uma alteração

```powershell
git add -A
git commit -m "descricao da mudanca"
git push
```

O Render republica sozinho em poucos minutos. **Os dados ficam**, porque o
banco está no Neon, fora do servidor do site.

---

## Custos

| Item | Preço |
|---|---|
| Render Free | US$ 0 (hiberna após 15 min parado) |
| Render Starter | US$ 7/mês (sem hibernação) |
| Neon Free | US$ 0 — 0,5 GB, cabem ~100 mil pedidos |
| Domínio `.com` | ~US$ 11/ano |

Medição real: 2.000 pedidos ocupam 3,7 MB, cerca de 1,9 KB cada.

---

## O que falta

1. **Upgrade do Render para Starter.** Sem isso o site dorme depois de 15
   minutos parado e a primeira visita demora uns 50 segundos.

2. **Corrigir o `render.yaml` depois do upgrade.** O arquivo diz `plan: free`
   e o Render sincroniza esse valor a cada publicação, então ele rebaixaria o
   plano de volta. Trocar para `plan: starter`.

3. **Comprar `verllog.com`** e ligar em Settings → Custom Domains. O Render
   emite o certificado HTTPS sozinho.

---

## Coisas que já quebraram (para não repetir)

- **Reimportar planilha sem coluna de data** resetava a timeline de todos os
  pedidos, porque data vazia virava "hoje". Hoje a data só muda se a planilha
  trouxer uma.
- **Linhas em branco no fim da planilha** eram contadas como erro, porque a
  coluna STATUS vinha preenchida até o fim. A detecção agora olha só as
  colunas que o sistema usa.
- **Cabeçalhos diferentes** (CLIENTE, CÓD RASTREIO, ENDEREÇO COMPLETO) são
  traduzidos pelo dicionário `SINONIMOS` no importador.
- **`<br>` no título** grudava palavras no celular quando escondido. Trocado
  por spans que viram texto corrido em tela estreita.
- **Menu sumia no celular** por um `display: none`. Agora recolhe num botão.
