import os
import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from gymadvisorai.agent.chatbot import answer

def main():
    print("GymAdvisorAI (type 'exit' to quit)")
    while True:
        q = input("\n> ").strip()
        if not q or q.lower() in {"exit", "quit"}:
            break
        print(answer(q))

if __name__ == "__main__":
    main()
