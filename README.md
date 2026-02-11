# GymAdvisorAI — Clean MVP (Agent + RAG + GraphRAG)

Ten projekt to **minimalne, punktodajne MVP** pod wymagania z „Technologii Generatywnych”:
- **UI** (Streamlit)
- **Agent LLM** z pętlą (plan → wybór narzędzia → obserwacja → refleksja → odpowiedź)
- **Tools**: Vector RAG, GraphRAG, Memory
- **Trace** (debug) widoczny w UI

> Cel: pokazać, że LLM jest **centralnym bytem decyzyjnym**, a RAG/GraphRAG to **narzędzia**.

## 1) Struktura

```
app/
  streamlit_app.py
core/
  agent.py
  llm.py
  prompts.py
  types.py
  utils.py
tools/
  vector_rag.py
  graph_rag.py
  memory.py
scripts/
  ingest_docs.py
  ingest_graph.py
data/
  docs/
  indexes/
  graph/
```

## 2) Szybki start

### a) Instalacja
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### b) Dodaj dane
- wrzuć pliki `.txt/.md` do `data/docs/`
- (opcjonalnie) uzupełnij `data/graph/edges.csv`

### c) Zbuduj indeksy
```bash
python scripts/ingest_docs.py
python scripts/ingest_graph.py
```

### d) Odpal UI
```bash
streamlit run app/streamlit_app.py
```

## 3) Co prowadzący ma zobaczyć

Agent wykonuje krótką pętlę:
1. **Intent**
2. **Tool choice** (Vector RAG vs GraphRAG)
3. **Observation**
4. **Reflection** (czy wystarczy? czy kolejna iteracja?)
5. **Answer** (uziemiona w obserwacji)

W UI jest sekcja **Agent reasoning (trace)** — to kluczowy artefakt.

## 4) RAG vs GraphRAG (krótko)

- **Vector RAG**: podobieństwo semantyczne fragmentów (opisy, fakty, rekomendacje).
- **GraphRAG**: relacje i ścieżki A→B→C (zależności, „co z czego wynika”).

## 5) Ograniczenia

- GraphRAG jest minimalny: działa offline na `edges.csv`/`graph.json`, opcjonalnie na Neo4j.
- Bez `OPENAI_API_KEY` działa **MockLLM** (żeby testować flow).

## Azure (opcjonalnie)

Jeśli chcesz użyć Azure OpenAI / Foundry, ustaw w `.env`:
- `LLM_PROVIDER=azure`
- `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`

W Azure parametr `model` to **nazwa deploymentu**.

