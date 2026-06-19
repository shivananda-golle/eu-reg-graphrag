# Regulation is a graph: building a GraphRAG assistant for the EU AI Act

Most RAG demos work because the questions are easy. You embed some documents, retrieve
the nearest chunks, and the model writes a fluent answer. It looks like magic until you
point it at something where the *structure* of the text carries meaning — and few things
are more structured than law.

I spend my days building retrieval systems, and I wanted a project that would force me to
deal with the hard version of RAG rather than the demo version. The EU AI Act turned out
to be the perfect adversary: it comes into force in August 2026, it's long, and it's
stitched together with cross-references. "High-risk AI systems referred to in Annex III."
"Without prejudice to Article 5." "The penalties laid down in Article 99." A single
obligation is smeared across an article, an annex it points to, and a penalty article
somewhere else entirely.

This is where plain vector search quietly fails, and where it gets interesting.

## The failure you don't notice

Here's the question I kept coming back to: *what makes an AI system high-risk?*

Run that through a normal vector RAG pipeline over the AI Act and you get a confident,
well-written, **wrong-ish** answer. The retriever pulls paragraphs that are full of the
words "high-risk AI systems" — resilience requirements, risk-management duties, testing
obligations. All genuinely about high-risk systems. None of them is **Article 6**, which
is the article that actually *defines* the classification, or **Annex III**, the list
Article 6 points to.

The model isn't hallucinating. It's faithfully summarizing the wrong context. The
bottleneck isn't generation — it's retrieval. Vector search matches on surface meaning,
and "what makes something high-risk" doesn't lexically resemble Article 6's actual
wording ("shall be considered high-risk where both conditions are fulfilled"). So the
right answer never makes it into the prompt.

The fix is to stop treating the regulation as a pile of paragraphs and start treating it
as what it is: a graph.

## Why a graph, and what kind

There's a spectrum of "graph" approaches in RAG. At one end, lexical graphs (LightRAG,
Microsoft's GraphRAG) use an LLM to *discover* entities and relationships in messy text.
That's the right tool when your corpus is unstructured and you don't know what the
entities are.

Law is the opposite problem. Its structure is already explicit and deterministic — every
article, paragraph, and annex is labeled — and its cross-references are written out in
plain text. Using an LLM to "extract" a graph from that would *add* noise, cost, and
non-determinism where none is needed. Worse, for a compliance tool it would undermine the
one thing that matters most: every claim has to be traceable to the source. "This edge
exists because the LLM thought so" is a terrible answer. "This edge exists because Article
6 literally says 'referred to in Annex III'" is a great one.

So I went with a **structural property graph**: nodes are the document's own units
(Article, Paragraph, Annex, Recital), edges are the hierarchy (`CONTAINS`) plus the
cross-references (`REFERENCES`). Five node types, two edge types. Every edge is provable
from the text.

The catch: those cross-references aren't hyperlinks in the source HTML. I checked — all
the internal links are footnotes. The references that matter ("Annex III", "Article 99")
live as prose. So building the graph meant writing a regex extractor that reads the text,
finds the references, and — importantly — skips the ones that point to *other* laws
("Article 9 **of Regulation (EU) 2016/679**" is not an internal edge). That one
distinction is the difference between 416 correct edges and a graph full of phantom links
to articles that don't exist in this regulation.

## The shape of the system

The whole thing runs in two phases.

**Build** turns the raw EUR-Lex HTML into one clean, structured JSON file (113 articles,
519 paragraphs, 180 recitals, 13 annexes), and from that single source builds two
indexes: a Neo4j knowledge graph and a Qdrant vector store. The trick that ties them
together is that every vector chunk carries the id of its corresponding graph node. Chunk
`006.001` is the same thing as graph node `006.001`. That shared key is what makes hybrid
retrieval possible later.

**Answer** is an agent. For each question it routes to one of three strategies:

- **vector** — semantic top-k, good for definitions and "what does X say"
- **graph** — find an entry node, then traverse `REFERENCES`, good for cross-references
- **hybrid** — seed from *both* vector and full-text search, then traverse; good for broad
  or multi-part questions

The router is a small LLM call. The generation is another. Everything in between —
the actual retrieval and graph traversal — is deterministic Cypher and vector search.
The model decides *how* to retrieve and *writes* the final answer, but it never
hand-traverses the graph. That keeps the system cheap (two LLM calls per question),
debuggable, and free of hallucinated reasoning paths. I wired it together with LangGraph.

Back to the high-risk question. Through graph retrieval, the full-text index finds Article
6 by its title ("Classification rules for high-risk AI systems"), the traversal follows
its reference to Annex III, and the answer comes back citing both — the operative rule and
the list. Same question, same model. The only thing that changed was teaching retrieval to
follow a reference.

## Does it actually work? Measure it.

It's easy to cherry-pick one good example. I wanted numbers.

I wrote a gold set of 13 questions across five categories — obligation lookup,
cross-reference, comparative, penalty/deadline, and definition — and anchored each to the
specific articles and annexes that *should* be retrieved. Then I ran every question
through all three strategies and scored two things: did retrieval surface the right
provisions (context recall, which is deterministic and needs no LLM), and how good was the
answer (faithfulness and correctness, scored by an LLM judge running on a *different*
model than the one that generated the answers, to avoid grading its own homework).

| Strategy | Context recall | Faithfulness | Correctness |
|----------|:--------------:|:------------:|:-----------:|
| Vector   | 0.38 | 0.78 | 0.63 |
| Graph    | 0.51 | 0.72 | 0.65 |
| Hybrid   | **0.82** | **0.88** | **0.83** |

Hybrid wins across the board, which is the headline. But the more interesting reading is
in the breakdown. On cross-reference questions, vector recall is essentially zero while
graph and hybrid recover the right provisions — that's the GraphRAG thesis, measured
rather than asserted. And vector turns out to be "faithful but wrong": it grounds its
answers well in whatever it retrieved, it just retrieved the wrong things.

## The part I'm proudest of: a failure I fixed

The eval also caught the system failing, which is the point of having one.

Definition questions scored 0.00 on retrieval. "What is a 'provider'?" couldn't find its
own answer. The cause was specific and a little embarrassing: Article 3 packs 68
definitions into a single paragraph, which became one 17,000-character chunk. My embedding
model truncates at 512 tokens, so everything past roughly the first ten definitions simply
wasn't in the vector. The provider definition was there in the data and invisible to
search.

The fix was to sub-chunk long, list-heavy paragraphs by their individual points, with a
bit of the parent paragraph's context prepended to each so it still embeds well on its
own. I re-chunked (830 → 1022 chunks, longest one down to 4,400 characters), re-embedded,
re-indexed, and re-ran the eval.

Definition recall went from **0.00 to 1.00**. Overall vector recall went from 0.12 to
0.38, hybrid from 0.67 to 0.82. "What is a provider?" now returns Article 3(3) as the top
hit.

That whole loop — measure, find a concrete failure, diagnose the root cause, fix it,
re-measure, watch the number move — is the thing I most wanted out of this project. It's
the difference between "I built a RAG app" and "I built a RAG system and I can tell you
exactly how good it is and why."

## What I'd be honest about

The corpus is the AI Act only, though the pipeline is built to be corpus-agnostic and
DORA and GDPR are next. Graph retrieval still under-performs on bare definition lookups,
because it seeds from a full-text index that chunking doesn't help — that needs better
entry ranking. Comparative questions ("how do obligations of providers differ from
deployers?") need multi-target retrieval I haven't built yet. And the whole thing runs on
CPU and free tiers, so embedding the corpus takes about fifteen minutes — I made it
checkpointed so it resumes if it dies halfway.

None of that bothers me. A portfolio project that claims to be perfect is a portfolio
project nobody believes.

## What I took away

The technical lesson is that retrieval, not generation, is usually where RAG quality
lives or dies, and that the right retrieval design depends entirely on the shape of your
data. For regulation, the structure *is* the signal, and throwing it away to chase
semantic similarity is the mistake.

The meta-lesson is about evaluation. Building the system was maybe 60% of the work. The
eval — and the failure it surfaced, and the fix — is what turned a demo into something I'd
actually trust enough to put in front of someone.

The code is on GitHub: every edge is provable from the source, every answer is cited, and
every number in this post is reproducible.
