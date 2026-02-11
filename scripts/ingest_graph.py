from dotenv import load_dotenv
import sys
from pathlib import Path

load_dotenv()

project_root = Path(__file__).parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.graph_rag import ingest_edges_to_json

if __name__ == "__main__":
    out = ingest_edges_to_json()
    print("OK:", out)
