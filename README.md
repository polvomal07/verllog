# Verllog Logística — Sistema de Rastreamento

Projeto acadêmico: sistema web completo de uma **transportadora fictícia**, com
site público de rastreamento e painel administrativo alimentado por planilha Excel.

> Todos os clientes, pedidos, códigos e eventos logísticos são fictícios.

## Arquitetura

```
Planilha Excel  ->  Painel /admin  ->  Importador (pandas)  ->  SQLite
                                                                  |
                                                    Motor de rotas + rastreamento
                                                                  |
                                                        Site publico (/)
```

O status de cada pedido **não é gravado manualmente**: ele é calculado na hora da
consulta, a partir da diferença entre a data atual e a `data_cadastro` do pedido.
Por isso o sistema funciona mesmo com o computador desligado por vários dias.

## Tecnologias

| Camada    | Ferramenta                 |
|-----------|----------------------------|
| Backend   | Python 3.12 + Flask        |
| Banco     | SQLite + SQLAlchemy        |
| Planilhas | pandas + openpyxl          |
| Frontend  | HTML, CSS e JavaScript     |
| Testes    | pytest                     |

## Código de rastreamento

Padrão obrigatório: `BR` + 12 números + 1 letra maiúscula (15 caracteres).

```
BR263198595496D
```

Validado por `CODIGO_REGEX` em `config.py` e único no banco de dados.

## Como rodar

```powershell
cd C:\Users\PICHAU\Documents\transportadora
.\.venv\Scripts\Activate.ps1
python app.py
```

Acesse http://127.0.0.1:5000

Para parar o servidor: `Ctrl + C`.

## Estrutura

```
transportadora/
├── app.py              ponto de entrada da aplicação
├── config.py           identidade, regras de código, fluxo de status
├── requirements.txt    dependências
├── models/             tabelas do banco (Fase 2)
├── services/           importador, rotas, rastreamento (Fases 3 a 7)
├── templates/          páginas HTML
├── static/             css, js e imagens
├── uploads/            planilhas enviadas pelo painel
└── tests/              testes automatizados (Fase 11)
```

## Fases do desenvolvimento

- [x] Fase 1 — Configuração do ambiente
- [x] Fase 2 — Banco de dados
- [x] Fase 3 — Importação do Excel e CSV
- [x] Fase 4 — Geração e validação dos códigos
- [x] Fase 5 — Motor de rastreamento
- [x] Fase 6 — Motor de rotas
- [x] Fase 7 — Atualização automática por data
- [ ] Fase 8 — Site público
- [ ] Fase 9 — Painel administrativo
- [ ] Fase 10 — Design profissional
- [ ] Fase 11 — Testes
- [ ] Fase 12 — Preparação para a apresentação

## Como colocar seus clientes no sistema

### 1. Exporte sua planilha

Aceita `.xlsx`, `.xls` ou `.csv`. No CSV o separador pode ser `,` ou `;`, e a
acentuação pode ser UTF-8 ou Windows-1252 — o sistema detecta sozinho.

Salve o arquivo dentro da pasta `uploads/`.

### 2. Colunas esperadas

| Coluna            | Obrigatória | Observação                                  |
|-------------------|-------------|---------------------------------------------|
| `codigo_rastreio` | sim         | se vier vazia, o sistema gera no padrão      |
| `nome`            | sim         |                                              |
| `cidade`          | sim         | define a rota logística                      |
| `estado`          | sim         | sigla de 2 letras (SP, RJ, ...)              |
| `cpf`             | não         | fica mascarado na página pública             |
| `endereco`        | não         |                                              |
| `numero`          | não         |                                              |
| `bairro`          | não         |                                              |
| `cep`             | não         |                                              |
| `data_cadastro`   | não         | `dd/mm/aaaa`; vazio assume hoje              |

Maiúsculas, acentos e espaços no cabeçalho não atrapalham: `Código Rastreio`,
`CODIGO_RASTREIO` e `codigo_rastreio` são tratados como a mesma coluna.

### 3. Confira antes de importar

```powershell
python -m flask conferir uploads\seu_arquivo.csv
```

Não grava nada. Mostra as colunas encontradas, o que falta e quais códigos
estão fora do padrão.

### 4. Importe

```powershell
python -m flask importar uploads\seu_arquivo.csv
```

Reimportar o mesmo arquivo não duplica: o código de rastreio é a chave, então
registros conhecidos são atualizados e só os inéditos entram.

## Comandos disponíveis

| Comando                              | O que faz                                  |
|--------------------------------------|--------------------------------------------|
| `python -m flask iniciar-banco`      | cria as tabelas                            |
| `python -m flask iniciar-banco --zerar` | apaga tudo e recria                     |
| `python -m flask conferir ARQUIVO`   | analisa a planilha sem gravar              |
| `python -m flask importar ARQUIVO`   | importa a planilha                         |
| `python -m flask listar`             | lista os pedidos com o status de hoje      |
| `python -m flask rastrear CODIGO`    | mostra a timeline completa no terminal     |

Antes de qualquer um deles, ative o ambiente e defina o app:

```powershell
.\.venv\Scripts\Activate.ps1
$env:FLASK_APP = "app.py"
```

## Scripts auxiliares

```powershell
python scripts\gerar_planilha_teste.py      # 20 clientes ficticios em 10 capitais
python scripts\gerar_planilhas_de_erro.py   # planilhas defeituosas para testar a validacao
python scripts\testar_motor.py              # confere determinismo e avanco por data
```
