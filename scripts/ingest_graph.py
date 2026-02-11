from dotenv import load_dotenv
load_dotenv()

from tools.graph_rag import ingest_edges_to_json

if __name__ == "__main__":
    out = ingest_edges_to_json()
    print("OK:", out)
