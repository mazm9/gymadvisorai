import streamlit as st
from dotenv import load_dotenv

from core.agent import Agent
from tools.memory import Memory

load_dotenv()

st.set_page_config(page_title="GymAdvisorAI", layout="wide")
st.title("GymAdvisorAI")
st.caption("Agent LLM + Vector RAG + GraphRAG + Trace.")

if "memory" not in st.session_state:
    st.session_state["memory"] = Memory()

agent = Agent(memory=st.session_state["memory"])

col1, col2 = st.columns([2, 1], gap="large")

with col1:
    q = st.text_area("Pytanie", height=120, placeholder="Np. Ułóż plan 3 dni pod hipertrofię, ale boli mnie bark. Wyjaśnij decyzje.")
    run = st.button("Uruchom agenta", type="primary")
    if run and q.strip():
        with st.spinner("Agent pracuje..."):
            res = agent.run(q.strip())

        st.subheader("Odpowiedź")
        st.write(res.answer)

        with st.expander("Agent reasoning (trace)", expanded=True):
            for step in res.trace:
                st.markdown(f"### Step {step.step}")
                st.markdown(f"**Intent:** {step.intent}")
                st.markdown(f"**Tool:** `{step.tool}`")
                st.markdown(f"**Tool input:** {step.tool_input}")
                st.markdown("**Observation:**")
                st.code(step.observation)
                st.markdown(f"**Reflection:** {step.reflection}")

with col2:
    st.subheader("Źródła (raw)")
    st.caption("Debug view: pokazuje, że agent korzysta z narzędzi.")
    if run and q.strip():
        st.session_state["last_sources"] = res.sources

    sources = st.session_state.get("last_sources")
    if sources:
        for s in sources:
            st.markdown(f"**{s.get('type')}**")
            st.code(s, language="json")
    else:
        st.info("Po uruchomieniu agenta zobaczysz tu zwrócone źródła.")
