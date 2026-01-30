* Getting Started
* Quickstart

On this page

# Quickstart

[View on GitHub](https://github.com/cocoindex-io/cocoindex-quickstart)
[Watch on YouTube](https://www.youtube.com/watch?v=gv5R8nOXsWU)

In this tutorial, we’ll build an index with text embeddings, keeping it minimal and focused on the core indexing flow.

## Flow Overview[​](#flow-overview "Direct link to Flow Overview")

![Flow](/docs/assets/images/flow-778aacc76eccd40ff3cedb3782bce4dd.png)

1. Read text files from the local filesystem
2. Chunk each document
3. For each chunk, embed it with a text embedding model
4. Store the embeddings in a vector database for retrieval

## Setup[​](#setup "Direct link to Setup")

1. Install CocoIndex:

   ```
   pip install -U 'cocoindex[embeddings]'
   ```
2. [Install Postgres](https://cocoindex.io/docs/getting_started/installation#-install-postgres).
3. Create a new directory for your project:

   ```
   mkdir cocoindex-quickstart  
   cd cocoindex-quickstart
   ```
4. Place input files in a directory `markdown_files`. You may download from [markdown\_files.zip](/docs/assets/files/markdown_files-f9fa042688f8855fa2912a9e144909fa.zip).

## Define a flow[​](#define-a-flow "Direct link to Define a flow")

Create a new file `main.py` and define a flow.

main.py

```
import cocoindex  
  
@cocoindex.flow_def(name="TextEmbedding")  
def text_embedding_flow(flow_builder: cocoindex.FlowBuilder, data_scope: cocoindex.DataScope):  
    # ... See subsections below for function body
```

### Add Source and Collector[​](#add-source-and-collector "Direct link to Add Source and Collector")

main.py

```
# add source  
data_scope["documents"] = flow_builder.add_source(  
    cocoindex.sources.LocalFile(path="markdown_files"))  
  
# add data collector  
doc_embeddings = data_scope.add_collector()
```

`flow_builder.add_source` will create a table with sub fields (`filename`, `content`)

[Source](https://cocoindex.io/docs/sources)
[Data Collector](https://cocoindex.io/docs/core/flow_def#data-collector)

### Process each document[​](#process-each-document "Direct link to Process each document")

With CocoIndex, it is easy to process nested data structures.

main.py

```
with data_scope["documents"].row() as doc:  
    # ... See subsections below for function body
```

#### Chunk each document[​](#chunk-each-document "Direct link to Chunk each document")

main.py

```
doc["chunks"] = doc["content"].transform(  
    cocoindex.functions.SplitRecursively(),  
    language="markdown", chunk_size=2000, chunk_overlap=500)
```

We extend a new field `chunks` to each row by *transforming* the `content` field using `SplitRecursively`. The output of the `SplitRecursively` is a KTable representing each chunk of the document.

[SplitRecursively](https://cocoindex.io/docs/ops/functions#splitrecursively)

![Chunking](/docs/assets/images/chunk-8885796037fcf540e8d0286570c1c1d0.png)

#### Embed each chunk and collect the embeddings[​](#embed-each-chunk-and-collect-the-embeddings "Direct link to Embed each chunk and collect the embeddings")

main.py

```
with doc["chunks"].row() as chunk:  
    # embed  
    chunk["embedding"] = chunk["text"].transform(  
        cocoindex.functions.SentenceTransformerEmbed(  
            model="sentence-transformers/all-MiniLM-L6-v2"  
        )  
    )  
  
    # collect  
    doc_embeddings.collect(  
        filename=doc["filename"],  
        location=chunk["location"],  
        text=chunk["text"],  
        embedding=chunk["embedding"],  
    )
```

This code embeds each chunk using the SentenceTransformer library and collects the results.

![Embedding](/docs/assets/images/embed-7287f1f708a86fe9ace964be7f60a11c.png)

[SentenceTransformerEmbed](https://cocoindex.io/docs/ops/functions#sentencetransformerembed)

### Export the embeddings to Postgres[​](#export-the-embeddings-to-postgres "Direct link to Export the embeddings to Postgres")

main.py

```
doc_embeddings.export(  
    "doc_embeddings",  
    cocoindex.storages.Postgres(),  
    primary_key_fields=["filename", "location"],  
    vector_indexes=[  
        cocoindex.VectorIndexDef(  
            field_name="embedding",  
            metric=cocoindex.VectorSimilarityMetric.COSINE_SIMILARITY,  
        )  
    ],  
)
```

CocoIndex supports other vector databases as well, with 1-line switch.

[Targets](https://cocoindex.io/docs/targets)

## Run the indexing pipeline[​](#run-the-indexing-pipeline "Direct link to Run the indexing pipeline")

* Specify the database URL by environment variable:

  ```
  export COCOINDEX_DATABASE_URL="postgresql://cocoindex:cocoindex@localhost:5432/cocoindex"
  ```

Prerequisite

Make sure your Postgres server is running before proceeding. See [how to launch CocoIndex](/docs/core/settings#configure-cocoindex-settings) for details.

* Build the index:

  ```
  cocoindex update main
  ```

CocoIndex will run for a few seconds and populate the target table with data as declared by the flow. It will output the following statistics:

```
documents: 3 added, 0 removed, 0 updated
```

That's it for the main indexing flow.

## End to end: Query the index (Optional)[​](#end-to-end-query-the-index-optional "Direct link to End to end: Query the index (Optional)")

If you want to build a end to end query flow that also searches the index, you can follow the [simple\_vector\_index](https://cocoindex.io/examples/simple_vector_index#query-the-index) example.

## Next Steps[​](#next-steps "Direct link to Next Steps")

Next, you may want to:

* Learn about [CocoIndex Basics](/docs/core/basics).
* Explore more of what you can build with CocoIndex in the [examples](https://cocoindex.io/examples) directory.

[Edit this page](https://github.com/cocoindex-io/cocoindex/tree/main/docs/docs/getting_started/quickstart.md)

[Previous

Overview](/docs/)[Next

Installation](/docs/getting_started/installation)

* [Flow Overview](#flow-overview)
* [Setup](#setup)
* [Define a flow](#define-a-flow)
  + [Add Source and Collector](#add-source-and-collector)
  + [Process each document](#process-each-document)
  + [Export the embeddings to Postgres](#export-the-embeddings-to-postgres)
* [Run the indexing pipeline](#run-the-indexing-pipeline)
* [End to end: Query the index (Optional)](#end-to-end-query-the-index-optional)
* [Next Steps](#next-steps)