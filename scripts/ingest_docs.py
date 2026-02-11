from dotenv import load_dotenv
load_dotenv()

from tools.vector_rag import ingest_docs

if __name__ == "__main__":
    out = ingest_docs("data/docs")
    print("OK:", out)
