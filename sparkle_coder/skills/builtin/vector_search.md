# Vector Search Mastery
Use vector search only where semantic similarity improves retrieval. Choose embedding model, distance metric, normalization, index type and metadata filters together. Benchmark against lexical or hybrid retrieval rather than assuming vectors are superior.

Store stable document/chunk identifiers and embedding-version metadata so reindexing is safe. Apply tenant/security filters before exposing results. Tune top-k and reranking with actual retrieval evaluation.

Master standard: index updates are reproducible, permission filters cannot be bypassed, and retrieval quality is measured on realistic queries.