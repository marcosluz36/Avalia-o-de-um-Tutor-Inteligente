# TutorIA local

Tutor de Circuitos Lógicos em Python, com Streamlit, RAG, apoio socrático e fontes
auditáveis. A geração de respostas usa somente o OpenRouter; a extração, os
embeddings e o banco são locais. Não há LangChain, agentes ou servidor de banco.

## Começar no Linux

Use Python 3.11 ou 3.12. Execute os comandos dentro da pasta extraída:

```bash
cd tutoria_local
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "torch>=2.6,<3" "torchvision>=0.21,<1" --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
python -m pip check
cp .env.example .env
python -m streamlit run app.py
```

Abra [http://localhost:8501](http://localhost:8501). Informe a chave no campo
protegido, abra **Materiais**, selecione um arquivo e clique em **Indexar
materiais**. O simples upload não inicia a indexação. Depois use **Chat**.

Definir `OPENROUTER_API_KEY` no ambiente ou preencher a cópia
local `.env`. O campo protegido, quando preenchido, tem precedência. Nenhuma chave
é incluída na exportação da conversa.

Para começar sem um livro, use `examples/circuitos_logicos.pdf`: são três páginas
de conteúdo didático original de teste, não um capítulo de livro. Há também uma
versão Markdown; indexe apenas uma versão para evitar duplicação intencional de
conteúdo em formatos diferentes.

## Comandos

Indexar o PDF de teste ou seus próprios materiais não exige chave de LLM:

```bash
python -m tutoria.cli index examples/circuitos_logicos.pdf
python -m tutoria.cli index "/caminho/livro.pdf" "/caminho/aula.pptx"
python -m tutoria.cli list
```

O mesmo conteúdo e a mesma configuração retornam `already_indexed`, inclusive se
o arquivo for renomeado. Extração, chunks e vetores têm caches separados. Mudanças
nos parâmetros de chat não provocam reindexação. Mudanças no título ou no mapa de
páginas podem reaproveitar os vetores se o texto de embedding permanecer idêntico.

Para declarar título e números impressos conhecidos, em um único PDF:

```bash
python -m tutoria.cli index examples/circuitos_logicos.pdf --title "Circuitos Lógicos - material de teste" --page-map examples/paginas_impressas.json
```

O mapa é um objeto JSON como `{"1":"41","2":"42","3":"43"}`. As chaves são
posições no PDF, começando em 1; os valores são rótulos impressos que **você
conferiu**. Essa informação fica marcada como `user_mapping`. Use os mesmos
parâmetros em futuras indexações para conservar esses metadados.

OCR pt/en, apenas quando necessário:

```bash
python -m pip install -r requirements-ocr.txt
python -m tutoria.cli index "/caminho/digitalizado.pdf" --ocr
```

Enriquecimento local de fórmulas e reprocessamento explícito:

```bash
python -m tutoria.cli index "/caminho/livro.pdf" --formulas
python -m tutoria.cli index "/caminho/livro.pdf" --force
```

`--force` refaz a extração, o chunking e os embeddings. Habilitar OCR ou fórmulas
altera a assinatura do pipeline; `--force` não é necessário apenas por isso.
OCR e enriquecimento podem baixar pesos adicionais e aumentar bastante o custo
de processamento. Na interface, essas opções ficam na aba Materiais.

Com a chave configurada no ambiente ou em `.env`:

```bash
python -m tutoria.cli models
python -m tutoria.cli ask "O que dizem os teoremas de De Morgan?" --k 4 --temperature 0.2 --max-tokens 300
python -m tutoria.cli ask "Qual a diferença entre latch e flip-flop?" --json > consulta.json
python -m tutoria.cli chunk ID_COMPLETO_DO_CHUNK
python -m tutoria.cli remove ID_COMPLETO_DO_DOCUMENTO
```

`ask` é uma consulta isolada. Para apoio progressivo com histórico, use o chat.
`remove` retira o documento da busca, preservando originais e caches. Respostas
anteriores conservam seus trechos no histórico/exportação. Arquivos diferentes
com o mesmo nome são documentos distintos: remova a versão antiga explicitamente
se não quiser consultar ambas.

## Arquivos do projeto

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Interface, upload explícito, parâmetros, histórico e fontes |
| `tutoria/config.py` | Ambiente, diretórios e formatos implementados |
| `tutoria/types.py` | Contratos de chunks, resultados e configurações |
| `tutoria/util.py` | Hashes, JSON atômico, caminhos e bloqueio local |
| `tutoria/extraction.py` | Conversão Docling e cache de extração |
| `tutoria/chunking.py` | HybridChunker e associação da proveniência |
| `tutoria/embeddings.py` | E5 local, limite e contrato imutável por base |
| `tutoria/store.py` | Coleção Chroma e manifesto de gerações publicadas |
| `tutoria/indexing.py` | Pipeline de ingestão e caches independentes |
| `tutoria/retrieval.py` | Consulta vetorial e continuidade curta |
| `tutoria/context.py` | Seleção de histórico/contexto dentro do orçamento |
| `tutoria/openrouter.py` | Catálogo, HTTP, parâmetros e erros seguros |
| `tutoria/citations.py` | Validação de referências |
| `tutoria/tutor.py` | Orquestração e fotografia de cada resposta |
| `tutoria/prompts/system.txt` | Política pedagógica e de fundamentação |
| `tutoria/cli.py` | Comandos de indexação, consulta e inspeção |
| `tests/test_contracts.py` | Testes offline com doubles das integrações |
| `tests/test_integration.py` | Teste real opcional do pipeline local |
| `examples/circuitos_logicos.pdf` | Material didático original de teste |
| `examples/circuitos_logicos.md` | Alternativa textual do mesmo material |
| `examples/paginas_impressas.json` | Mapa declarado para conferir a paginação |
| `scripts/create_fixture.py` | Regenera o PDF; requer ReportLab, fora do app |
| `requirements.txt` | Dependências da aplicação |
| `requirements-ocr.txt` | Dependência opcional de OCR |
| `.env.example` / `.streamlit/config.toml` | Configuração inicial sem credenciais |
| `VALIDACAO.md` | Evidências executadas, roteiro e validações pendentes |
| `TEST_RESULTS.txt` | Saída da execução dos testes offline nesta entrega |

Dentro de `data/`, a aplicação cria `originals/`, `extractions/`, `chunks/`,
`embeddings/`, `chroma/`, `manifest.json` e `embedding_profile.json`. Faça backup
da pasta completa quando não houver indexação em andamento.

Os vetores são inseridos em uma geração nova e só passam a ser consultados após
a publicação atômica do manifesto. Uma inserção parcial não entra na busca. A
geração antiga é removida depois do commit. Chroma e JSON **não constituem uma
transação ACID única**; cópias completas da pasta e o teste real continuam
necessários. Um lock local serializa as operações; não é uma arquitetura para
múltiplas máquinas nem para pastas em sistemas de arquivos de rede.

## Configuração e limites

| Opção | Padrão | Efeito |
|---|---|---|
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Seleção inicial do dropdown se o ID estiver entre as quatro opções; caso contrário, usa gpt-4o-mini |
| Temperatura | `0.2` | Aplicada quando suportada |
| k | `4` | Quantidade máxima de chunks recuperados; não envia `top_k` à LLM |
| Teto de saída | `300` | Máximo pedido, limitado às capacidades publicadas |
| Similaridade mínima | `0.75` | Filtro heurístico antes da geração |
| `TUTORIA_DATA_DIR` | `data/` junto de `app.py` | Pasta persistente |
| `TUTORIA_CHUNK_TOKENS` | `480` | Orçamento do chunker, entre 64 e 480 |
| `TUTORIA_EMBED_BATCH_SIZE` | `16` | Lote dos embeddings em CPU |
| `TUTORIA_EMBED_REVISION` | `main` inicialmente | Resolvida e fixada no perfil da base |
| `TUTORIA_OCR` | `false` | OCR pt/en para PDFs |
| `TUTORIA_FORMULAS` | `false` | Enriquecimento de fórmulas para PDFs |

O histórico é mantido na sessão Streamlit durante alterações de widgets e pode
ser exportado em JSON. Não é salvo automaticamente no disco e não há importação
de histórico nesta versão. Uma nova sessão, desconexão que encerre a sessão ou
reinício do servidor pode perder a conversa; a base vetorial permanece.

O prompt de sistema está em arquivo próprio. Os documentos chegam em uma mensagem
de referência JSON com papel de usuário, separados das regras. O tutor não
recebe ferramentas de execução. Essa separação reduz a superfície de injeção de
prompt, mas não garante obediência de toda LLM; confira o roteiro adversarial.

Não há compreensão visual de esquemas, verificador algébrico, reranker, busca
lexical, avaliação RAGAS ou índice de sinônimos/T12. Tabelas, negações e fórmulas
extraídas precisam ser revisadas. Conversões parciais são recusadas; uma
conversão marcada como sucesso ainda pode conter erros ou páginas sem texto.
Não há garantia de que definições e exemplos distantes permaneçam no mesmo chunk.

O projeto é pequeno no código, mas Docling e modelos neurais não são dependências
leves. Comece com poucas páginas e lote 16 ou 8 em CPU. Não há processamento de
livros inteiros em streaming nesta versão: documento, chunks e vetores do
arquivo ficam em memória durante a indexação. O limite de upload não é uma
garantia de uso de RAM. Divida arquivos grandes em materiais identificáveis.
