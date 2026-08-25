# Colocar o site no ar

Guia completo, do zero até o link público funcionando.

Você vai usar dois serviços, os dois gratuitos:

| Serviço   | Para quê                          | Custo |
|-----------|-----------------------------------|-------|
| **Neon**  | Banco de dados PostgreSQL         | Grátis, sem prazo |
| **Render**| Hospedar o site                   | Grátis |

O banco fica **separado** do site. É isso que faz os dados sobreviverem a
atualizações, reinícios e hibernação. Se o banco ficasse dentro do servidor,
cada atualização apagaria tudo.

---

## Etapa 1 — Criar o banco de dados (Neon)

1. Acesse **https://neon.tech** e crie uma conta (dá para entrar com o Google).
2. Clique em **Create project**.
   - Nome: `verllog`
   - Região: **AWS São Paulo** (`sa-east-1`), para o site responder mais rápido.
3. Terminado, aparece uma caixa **Connection string**. Copie o texto inteiro.
   Ele se parece com:

   ```
   postgresql://verllog_owner:AbC123xyz@ep-nome-12345.sa-east-1.aws.neon.tech/verllog?sslmode=require
   ```

4. **Guarde essa linha.** Você vai colar no Render na Etapa 3.

> Essa string é a senha do seu banco. Não coloque em nenhum arquivo do projeto
> nem mande para ninguém.

---

## Etapa 2 — Subir o código para o GitHub

1. Crie uma conta em **https://github.com** se ainda não tiver.
2. Clique em **New repository**.
   - Nome: `verllog`
   - Deixe em **Private** se não quiser o código visível para todos.
   - **Não** marque "Add a README" (o projeto já tem um).
3. Na tela seguinte, o GitHub mostra o endereço do repositório. Copie.
4. No PowerShell, dentro da pasta do projeto:

   ```powershell
   cd C:\Users\PICHAU\Documents\transportadora
   git branch -M main
   git remote add origin https://github.com/SEU-USUARIO/verllog.git
   git push -u origin main
   ```

   Troque `SEU-USUARIO` pelo seu nome de usuário do GitHub. Na primeira vez o
   Git vai abrir uma janela pedindo para você entrar na conta.

O banco local (`database.db`) e as planilhas da pasta `uploads/` **não sobem**:
estão no `.gitignore`, porque contêm dados de clientes.

---

## Etapa 3 — Publicar o site (Render)

1. Acesse **https://render.com** e crie a conta entrando com o GitHub.
2. No painel, clique em **New +** e escolha **Blueprint**.
3. Selecione o repositório `verllog`. O Render lê o arquivo `render.yaml` e já
   monta o serviço sozinho.
4. Ele vai pedir os valores das variáveis. Preencha:

   | Variável        | O que colocar |
   |-----------------|---------------|
   | `DATABASE_URL`  | a connection string do Neon (Etapa 1) |
   | `ADMIN_USUARIO` | o usuário do painel, por exemplo `admin` |
   | `ADMIN_SENHA`   | **uma senha forte e nova** |

5. Clique em **Apply**. A primeira publicação leva de 3 a 5 minutos.
6. Quando terminar, o Render mostra o endereço do site:

   ```
   https://verllog.onrender.com
   ```

As tabelas do banco são criadas sozinhas na primeira vez que o site sobe.

---

## Etapa 4 — Carregar seus pedidos

1. Acesse `https://verllog.onrender.com/admin`
2. Entre com o usuário e a senha que você definiu na Etapa 3.
3. Em **Importar nova planilha**, envie o seu CSV.
4. Confira o relatório: adicionados, atualizados, linhas em branco e erros.

Pronto. O site está no ar e os códigos já podem ser consultados.

---

## O dia a dia depois disso

### Enviar novos pedidos

Sempre pelo painel: `/admin` → **Importar nova planilha**.

Reenviar o mesmo arquivo **não duplica nada**. O código de rastreio é a chave:
pedidos já conhecidos são atualizados, e só os novos entram. Então você pode
mandar a planilha inteira toda vez, sem precisar separar o que é novo.

### O rastreio se atualiza sozinho

Nada precisa ficar rodando. Cada pedido tem as movimentações gravadas com data
e hora; o site mostra as que já passaram. O ciclo é de 35 dias, com a tentativa
de entrega frustrada no dia 28 e a nova tentativa no dia 30.

### Alterar o código do site

```powershell
git add -A
git commit -m "descricao da mudanca"
git push
```

O Render republica sozinho em poucos minutos. **Os dados no banco permanecem**,
porque o banco está no Neon, fora do servidor.

---

## Coisas que valem saber

**O site hiberna.** No plano gratuito do Render, depois de 15 minutos sem
acesso o serviço dorme, e a primeira visita seguinte demora cerca de 50
segundos para carregar. Depois disso fica rápido. Se for apresentar para
alguém, abra o site uns minutos antes para "acordar". O plano pago (US$ 7/mês)
remove isso.

**Backup do banco.** O Neon guarda histórico dos últimos dias no plano
gratuito, mas não confie só nisso: guarde os seus CSVs originais. Com eles você
reconstrói o banco inteiro em um upload.

**Senha do painel.** O `/admin` fica acessível na internet. Use uma senha longa
e diferente das suas outras. Para trocar depois: Render → seu serviço →
**Environment** → editar `ADMIN_SENHA` → **Save**.

**Fuso horário.** O `render.yaml` já define `TZ=America/Manaus`. Sem isso o
servidor rodaria em UTC e as datas do rastreio sairiam algumas horas adiantadas.

**Domínio próprio.** Se quiser trocar `verllog.onrender.com` por
`verllog.com.br`, registre o domínio no Registro.br (cerca de R$ 40 por ano) e
aponte no Render em **Settings → Custom Domain**. O certificado HTTPS é emitido
automaticamente.

---

## Se der errado

**A publicação falhou no Render.** Abra a aba **Logs** do serviço. O erro quase
sempre aparece nas últimas linhas.

**O site abre mas dá erro ao buscar um código.** Provavelmente a `DATABASE_URL`
está errada ou incompleta. Confira se copiou a string inteira do Neon, incluindo
o `?sslmode=require` no final.

**O painel diz que o banco está vazio.** Normal na primeira vez: as tabelas
foram criadas, mas nenhum pedido foi importado ainda. Faça a Etapa 4.

**Esqueci a senha do painel.** Render → Environment → defina uma nova
`ADMIN_SENHA` → Save. O serviço reinicia sozinho e os dados continuam lá.
