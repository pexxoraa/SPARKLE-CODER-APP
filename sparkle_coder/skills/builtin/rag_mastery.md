# RAG & Knowledge Retrieval Mastery
Design retrieval around the question and corpus, not around “add embeddings.” Define chunking, metadata, freshness, access control, ranking, query rewriting and citation/provenance rules deliberately. Use lexical, semantic or hybrid retrieval according to evidence.

Do not stuff the full corpus into context. Retrieve a bounded candidate set, rerank when needed, and preserve source identity. Separate “no evidence found” from “answer is false.” Ensure retrieval enforces the same tenant/document permissions as the application.

Master standard: evaluation measures retrieval quality separately from generation quality, answers can point back to evidence, stale/private documents do not leak, and missing evidence produces an honest result.