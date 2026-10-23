# 03 System Design Document (SDD)

| Field | Value |
|---|---|
| Product | FlameAtlas |
| Document owner | Syed Mehedi Hussain (Integration and QA) |
| Contributors | Md. Mahmudul Hasan, Opi Mojumdar, Aurin Subah |
| Status | Baseline v1.0 |
| Related | [TRD](02-TRD.md), [Data spec](05-data-spec.md), [AI/RAG spec](06-ai-rag-spec.md) |

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-24 | First baseline |

---

## 1. Design overview

FlameAtlas has two halves that never run at the same time:

1. **An offline pipeline** that turns NASA sources into a hand-checked evidence base. It runs on a developer laptop before the demo.
2. **An online app** that reads the evidence base and answers users. It runs on Streamlit Community Cloud.

The only bridge between them is a set of committed files: `data/curated/*.csv`, `data/processed/cards.jsonl` and `data/processed/chroma/`. Because the map, the cards and the assistant all read those same files, they cannot disagree.

Three design principles drive every choice below:

| Principle | What it means in the design |
|---|---|
| **A person checks, the AI proposes** | The language model only ever produces *candidate* records. A record reaches the map only after the Data and Science Lead marks it `verified`. |
| **Deterministic where it matters** | Habitat status and answer confidence are computed by plain Python rules, not by the language model, so they are repeatable and explainable. |
| **Fail toward honesty** | Whenever data is missing or out of range, the system says `UNTESTED`, `NO BOUNDARY` or `GAP` instead of guessing. |

## 2. System context (C4 level 1)

```mermaid
flowchart TB
    user(["Habitat engineer, safety analyst,<br/>researcher or judge"])
    dl(["Data and Science Lead"])
    fa["FlameAtlas<br/>web app and evidence base"]
    psi[("NASA PSI<br/>experiment archive")]
    ntrs[("NASA NTRS<br/>technical reports")]
    llm["Anthropic Claude API"]
    host["Streamlit Community Cloud"]

    user -->|"explores map, reads cards,<br/>asks questions (HTTPS)"| fa
    dl -->|"verifies extracted records"| fa
    fa -->|"downloads test logs and documents<br/>(offline, once)"| psi
    fa -->|"downloads papers (offline, once)"| ntrs
    fa -->|"extraction, question parsing,<br/>cited answers"| llm
    host -->|"runs"| fa
```

*Figure 1. FlameAtlas and the people and systems around it. NASA systems are only contacted by the offline pipeline.*

## 3. Containers (C4 level 2)

```mermaid
flowchart LR
    subgraph offline["Offline pipeline (developer laptop)"]
        fetch["Fetch scripts<br/>fetch_psi.py, fetch_ntrs.py"]
        chunk["Chunker<br/>PDF text to page-tagged passages"]
        extract["Extractor<br/>Claude batch, structured output"]
        review["Review sheet<br/>records.csv edited by Data Lead"]
        validate["Validator<br/>validate_records.py"]
        build["Builder<br/>flameatlas.build"]
    end
    subgraph files["Committed evidence base"]
        curated[("data/curated<br/>materials, sources, records")]
        cards[("data/processed/cards.jsonl")]
        chroma[("data/processed/chroma<br/>passage index")]
    end
    subgraph online["Online app (Streamlit Cloud)"]
        ui["Streamlit UI<br/>Map, Evidence, Ask tabs"]
        core["Core logic<br/>boundary, classify, confidence"]
        rag["RAG service<br/>parse, retrieve, answer"]
        guard["LLM client<br/>timeouts, retries, spend guard"]
    end
    raw[("data/raw<br/>PSI and NTRS files")]
    claude["Claude API"]

    fetch --> raw --> chunk
    chunk --> extract --> review --> validate --> curated
    curated --> build
    chunk --> build
    build --> cards
    build --> chroma
    extract --> claude
    curated --> core
    cards --> ui
    chroma --> rag
    curated --> rag
    ui --> core
    ui --> rag
    rag --> core
    rag --> guard --> claude
```

*Figure 2. Containers. Solid boxes are processes; cylinders are files. The committed evidence base is the contract between the two halves.*

| Container | Technology | Responsibility | Owner |
|---|---|---|---|
| Fetch scripts | Python standard library | Reproducible download of PSI and NTRS data | Syed Mehedi Hussain |
| Chunker | PyMuPDF | Split each PDF into passages tagged with source and page | Md. Mahmudul Hasan |
| Extractor | Claude Message Batches, pydantic | Propose candidate records and one card per source | Md. Mahmudul Hasan |
| Review sheet | CSV in a spreadsheet | Human verification of every candidate record | Aurin Subah |
| Validator | pydantic, pandas | Schema, unit-range and cross-reference checks | Aurin Subah |
| Builder | Python | Rebuild cards and the Chroma index from verified data | Syed Mehedi Hussain |
| Streamlit UI | Streamlit, Plotly | Three tabs, sliders, map, cards, chat | Opi Mojumdar |
| Core logic | scikit-learn, NumPy | Boundary fit, envelope, habitat status, nearest tests, confidence | Aurin Subah (science), Opi Mojumdar (integration) |
| RAG service | ChromaDB, Claude | Question parsing, retrieval, cited answers, gap flags | Md. Mahmudul Hasan |
| LLM client | `anthropic` SDK | One place for model IDs, timeouts, retries, cost tracking | Md. Mahmudul Hasan |

## 4. Components inside the app

```mermaid
flowchart TB
    app["app.py"]
    subgraph ui["flameatlas.ui"]
        mapv["map_view"]
        cardv["card_view"]
        askv["ask_view"]
    end
    subgraph core["flameatlas.core"]
        boundary["boundary"]
        classify["classify"]
        conf["confidence"]
    end
    subgraph rag["flameatlas.rag"]
        retrieve["retrieve"]
        answer["answer"]
        index["index"]
    end
    store["flameatlas.store"]
    schema["flameatlas.schema"]
    llm["flameatlas.llm"]
    config["flameatlas.config"]

    app --> mapv & cardv & askv
    mapv --> boundary & classify & store
    cardv --> store
    askv --> answer
    answer --> retrieve & conf & llm & store
    retrieve --> index
    boundary & classify & conf & store --> schema
    llm --> config
    index --> config
    store --> config
```

*Figure 3. Python modules and their imports. Arrows point from the importer to the imported module. `core` never imports `ui`, `rag` or `llm`, which keeps it testable without Streamlit or the network.*

## 5. Domain model

```mermaid
classDiagram
    class Material {
        +str material_id
        +str display_name
        +MaterialCategory category
        +str description
        +list~str~ aliases
    }
    class Source {
        +str source_id
        +SourceKind kind
        +str title
        +str authors
        +int year
        +str url
        +str license
    }
    class TestRecord {
        +str record_id
        +str material_id
        +str source_id
        +str source_locator
        +str experiment
        +Geometry geometry
        +float thickness_mm
        +float o2_pct
        +float pressure_kpa
        +float flow_cm_s
        +FlowDirection flow_direction
        +GravityRegime gravity
        +Outcome outcome
        +float spread_rate_mm_s
        +ExtractionMethod method
        +RecordStatus status
        +str verified_by
        +date verified_on
    }
    class EvidenceCard {
        +str card_id
        +str source_id
        +str experiment
        +list~str~ material_ids
        +ConditionsSummary conditions
        +str outcome_summary
        +str key_finding
        +str safety_takeaway
        +list~str~ record_ids
        +RecordStatus status
    }
    class Passage {
        +str chunk_id
        +str source_id
        +int page
        +str text
        +list~str~ material_ids
    }
    class BoundaryModel {
        +str material_id
        +FlowDirection direction
        +p_burn(o2, flow) float
        +in_envelope(o2, flow) bool
        +contour(level) list
    }
    class ParsedQuestion {
        +str material_id
        +float o2_pct
        +float pressure_kpa
        +float flow_cm_s
        +GravityRegime gravity
        +bool in_scope
    }
    class Answer {
        +str text
        +list~Citation~ citations
        +Confidence confidence
        +str confidence_reason
        +str gap_message
    }

    Material "1" --> "*" TestRecord : tested in
    Source "1" --> "*" TestRecord : reports
    Source "1" --> "1" EvidenceCard : summarized by
    EvidenceCard "1" --> "*" TestRecord : supports
    Source "1" --> "*" Passage : split into
    BoundaryModel "1" ..> "*" TestRecord : fitted from
    Answer "1" ..> "*" Passage : cites
    Answer "1" ..> "1" ParsedQuestion : answers
```

*Figure 4. UML class diagram of the domain model. Enumerations are listed in the [data spec](05-data-spec.md#4-schemas). Solid arrows are associations stored in the data; dashed arrows are runtime dependencies.*

### 5.1 Storage view (entity relationship)

```mermaid
erDiagram
    MATERIAL ||--o{ TEST_RECORD : "is tested in"
    SOURCE ||--o{ TEST_RECORD : "reports"
    SOURCE ||--|| EVIDENCE_CARD : "is summarized by"
    EVIDENCE_CARD ||--o{ CARD_RECORD : "lists"
    TEST_RECORD ||--o{ CARD_RECORD : "appears in"
    SOURCE ||--o{ PASSAGE : "is split into"
    MATERIAL {
        string material_id PK
        string display_name
        string category
    }
    SOURCE {
        string source_id PK
        string kind
        string title
        string url
    }
    TEST_RECORD {
        string record_id PK
        string material_id FK
        string source_id FK
        float o2_pct
        float flow_cm_s
        float pressure_kpa
        string outcome
        string status
    }
    EVIDENCE_CARD {
        string card_id PK
        string source_id FK
        string key_finding
        string status
    }
    CARD_RECORD {
        string card_id FK
        string record_id FK
    }
    PASSAGE {
        string chunk_id PK
        string source_id FK
        int page
    }
```

*Figure 5. Entity relationships as stored in CSV, JSONL and Chroma metadata. `CARD_RECORD` is the `record_ids` list inside each card.*

## 6. Key interactions

### 6.1 Moving a habitat slider

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Streamlit map_view
    participant C as st.cache_resource
    participant B as core.boundary
    participant K as core.classify
    participant P as Plotly

    U->>UI: drag oxygen slider to 34%
    UI->>C: get BoundaryModel(material, direction)
    alt first use after start
        C->>B: fit_boundary(verified records)
        B-->>C: BoundaryModel or None
    end
    C-->>UI: model
    UI->>K: classify_habitat(model, 34, flow)
    K->>B: in_envelope(34, flow)
    B-->>K: false
    K-->>UI: UNTESTED
    UI->>K: nearest_tests(records, 34, flow, pressure)
    K-->>UI: 3 records with distances
    UI->>P: figure(points, contour, envelope, habitat marker)
    P-->>U: updated map and status "UNTESTED"
```

*Figure 6. Slider interaction. The model is fitted once per material and flow direction; each slider move costs one classification and one redraw (target under 300 ms).*

### 6.2 Asking a question

```mermaid
sequenceDiagram
    actor U as User
    participant A as ask_view
    participant Q as rag.answer
    participant L as llm (Claude)
    participant R as rag.retrieve
    participant S as store
    participant F as core.confidence

    U->>A: "Is cotton fabric safe in a lunar habitat with low airflow?"
    A->>A: check session limit and daily budget
    A->>Q: answer_question(text)
    Q->>L: parse (structured output, effort low)
    L-->>Q: ParsedQuestion(material=sibal, gravity=lunar, flow=5)
    alt out of scope
        Q-->>A: fixed out-of-scope message
    else in scope
        par
            Q->>S: verified records for sibal
            S-->>Q: records
        and
            Q->>R: retrieve(text, material=sibal)
            R-->>Q: up to 8 passages above threshold
        end
        Q->>F: confidence_level(parsed, records, passages)
        F-->>Q: level and reason
        alt level is GAP
            Q-->>A: gap flag, no model call
        else HIGH, MEDIUM or LOW
            Q->>L: passages as cited documents, records as table
            L-->>Q: answer text with citations
            Q->>Q: reject if no citation
            Q-->>A: Answer(text, citations, level, reason)
        end
    end
    A-->>U: answer, confidence badge, expandable quotes
```

*Figure 7. Ask flow. Confidence is computed before generation, so a `GAP` result never calls the model to write an answer.*

### 6.3 Extracting and verifying a source

```mermaid
sequenceDiagram
    actor D as Data and Science Lead
    participant X as extract.run
    participant L as Claude Batches API
    participant E as data/extracted
    participant V as validate_records.py
    participant C as data/curated
    participant B as flameatlas.build

    X->>X: chunk PDFs into page-tagged text
    X->>L: one batch request per source (schema, effort high)
    L-->>X: candidate records and card per source
    X->>E: cache <source_id>.json
    X->>C: append candidates to records.csv as status=extracted
    D->>C: open records.csv, check each row against the locator
    D->>C: set status verified or rejected, fix values, sign verified_by
    D->>V: run validator
    alt errors
        V-->>D: list of row-level errors
    else clean
        V-->>D: OK, n verified records
        D->>B: build
        B->>B: cards from verified sources, rebuild Chroma index
    end
```

*Figure 8. The human check sits between the model and the map. Nothing marked `extracted` or `rejected` is ever drawn.*

## 7. Pipeline activity

```mermaid
flowchart TD
    start([Start]) --> f1[Run fetch scripts]
    f1 --> f2{All files present?}
    f2 -- "no, NASA file missing" --> f3[Record in manifest,<br/>continue] --> c1
    f2 -- yes --> c1[Chunk PDFs by page]
    c1 --> x1[Batch extraction with Claude]
    x1 --> x2{Schema valid?}
    x2 -- no --> x3[Log and retry once<br/>with error feedback] --> x2b{Valid now?}
    x2b -- no --> x4[Mark source for manual entry]
    x2b -- yes --> r1
    x2 -- yes --> r1[Candidates to records.csv]
    x4 --> r1
    r1 --> h1[Data Lead checks each row<br/>against its locator]
    h1 --> h2{Value matches source?}
    h2 -- yes --> h3[status = verified]
    h2 -- "fixable" --> h4[Correct value,<br/>note correction] --> h3
    h2 -- "not in source" --> h5[status = rejected]
    h3 --> v1[Run validator]
    h5 --> v1
    v1 --> v2{Errors?}
    v2 -- yes --> h1
    v2 -- no --> b1[Build cards and index]
    b1 --> m1[Measure extraction accuracy]
    m1 --> done([Commit evidence base])
```

*Figure 9. Activity diagram of the offline pipeline, including the two failure paths: NASA files that no longer exist and model output that fails the schema.*

## 8. Lifecycles

### 8.1 Test record

```mermaid
stateDiagram-v2
    [*] --> extracted : model proposes
    [*] --> manual : Data Lead enters from table or figure
    manual --> extracted : saved to records.csv
    extracted --> verified : matches source
    extracted --> corrected : value fixed by reviewer
    corrected --> verified : reviewer signs
    extracted --> rejected : not supported by source
    verified --> extracted : source re-read finds problem
    rejected --> [*]
    verified --> [*] : published to map
```

*Figure 10. Record states. `corrected` is recorded in the `notes` column; the stored `status` value is one of `extracted`, `verified`, `rejected`.*

### 8.2 Ask request

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Blocked : session limit or daily budget reached
    Idle --> Parsing : question submitted
    Parsing --> OutOfScope : not about materials or fire
    Parsing --> Retrieving : in scope
    Parsing --> Error : API error or timeout
    Retrieving --> Scoring
    Scoring --> Gap : confidence GAP
    Scoring --> Generating : HIGH, MEDIUM or LOW
    Generating --> Checking
    Generating --> Error : API error or timeout
    Checking --> Answered : at least one citation
    Checking --> Gap : no citations returned
    Answered --> Idle
    Gap --> Idle
    OutOfScope --> Idle
    Error --> Idle
    Blocked --> [*]
```

*Figure 11. States of one Ask request as shown to the user.*

## 9. Deployment

```mermaid
flowchart LR
    subgraph dev["Developer laptop"]
        repo["Git working copy"]
        pipe["Offline pipeline"]
    end
    subgraph gh["GitHub"]
        main["MahmudulHasanJoy/FlameAtlas<br/>branch main"]
    end
    subgraph cloud["Streamlit Community Cloud"]
        ctr["App container<br/>Python 3.11"]
        sec[("Secrets<br/>ANTHROPIC_API_KEY,<br/>budget settings")]
        files[("Bundled evidence base<br/>curated CSV, cards, Chroma")]
    end
    browser(["User browser"])
    anth["api.anthropic.com"]

    pipe --> repo -->|git push| main
    main -->|auto deploy on push| ctr
    sec --> ctr
    files --> ctr
    browser -->|HTTPS| ctr
    ctr -->|HTTPS, server side only| anth
```

*Figure 12. Deployment view. The API key exists only in the host's secret store; the browser never talks to the Claude API directly.*

## 10. Cross-cutting design

### 10.1 Caching

| What | Where | Invalidation |
|---|---|---|
| Curated tables, cards | `st.cache_data`, keyed by file modification time | New deploy or file change |
| Boundary models | `st.cache_resource`, keyed by material and flow direction | New deploy |
| Chroma client | `st.cache_resource`, one per process | New deploy |
| Extraction results | `data/extracted/<source_id>.json` | `--force` flag |
| Daily spend counter | `st.cache_resource` dictionary keyed by UTC date, mirrored to `logs/spend.jsonl` | Date change |

### 10.2 Error handling

| Failure | Detected by | User sees | System does |
|---|---|---|---|
| Claude API 429 or 5xx | SDK exception | "The assistant is busy; try again in a minute." | Two retries with backoff, then give up |
| Claude API timeout (30 s) | Timeout | Same message | Logged |
| Missing API key | Config check at start | Ask tab shows "Assistant not configured"; map and cards work | Logged once |
| Budget exhausted | Spend guard | "Today's question budget is used up. The map and evidence cards still work." | Ask disabled until UTC midnight |
| Schema error in curated data | Validator at load | App shows "Data error in records.csv row 42: o2_pct out of range" | App stops loading that file; other tabs still load |
| No verified records for material | `store` query | Empty state on map | Nothing else |
| Model returns no citations | Answer check | Gap message | Answer discarded and logged |

### 10.3 Security

- The API key is read from the environment or Streamlit secrets and used only in `flameatlas/llm.py`.
- System prompts are constants. User text is placed inside a delimited block in the user turn (see [AI/RAG spec](06-ai-rag-spec.md#7-prompt-design)).
- Retrieved passages come only from the committed NASA corpus, so the indirect prompt-injection surface is limited to NASA documents.
- No user data is stored beyond the session; logs in the hosted app omit question text.

### 10.4 Observability

Each request logs one JSON line (TR-20). During the hackathon the team watches the Streamlit Cloud log stream; after the demo the spend log is checked against the Anthropic console.

## 11. Design decisions summary

Full reasoning lives in the [decision log](10-decisions.md).

| Decision | Chosen | Main alternative rejected |
|---|---|---|
| UI framework | Streamlit | React with a Python API (two codebases in 48 hours) |
| Grounding | RAG over a local Chroma index | Model's own knowledge (unverifiable); MCP server (setup cost, no visible benefit) |
| Language model | Claude Opus 5.5 with native citations | Other providers (no native citation spans) |
| Boundary | Logistic regression on O2, ln(flow), ln(flow)² with a tested envelope | Hand-drawn curve only (not reproducible) |
| Habitat labels | Four states including `UNTESTED`, no "Safe" label | Safe / Danger (overclaims safety) |
| Confidence | Deterministic rule | Model self-reported confidence (not calibrated) |
| Extraction input | Page-tagged text | Whole PDFs (several times more tokens per page) |
