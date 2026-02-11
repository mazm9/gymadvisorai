from dotenv import load_dotenv
import sys
from pathlib import Path

load_dotenv()

project_root = Path(__file__).parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.pdf_to_graph import extract_graph_from_docs

if __name__ == "__main__":
    out = extract_graph_from_docs()
    print("OK:", out)
