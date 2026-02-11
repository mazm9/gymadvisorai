import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

_project_root = Path(__file__).parent.parent.absolute()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st
from dotenv import load_dotenv

from core.agent_full import AgentFull
from core.llm import get_llm
from tools.memory import Memory
from tools.data_loader import load_project_data

load_dotenv()

st.set_page_config(page_title="GymAdvisor", layout="wide")
st.title("GymAdvisor")
st.caption("Dobór ćwiczeń i planów na podstawie profilu, katalogu ćwiczeń oraz bazy wiedzy (dokumenty/graf).")

if "memory" not in st.session_state:
    st.session_state["memory"] = Memory()
if "last_debug" not in st.session_state:
    st.session_state["last_debug"] = {}

llm = get_llm()
agent_full = AgentFull(llm=llm)
loaded = load_project_data(".")


def _persist_active_profile(profile: dict) -> None:
    os.makedirs("data/input", exist_ok=True)
    with open("data/input/profile.json", "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def _set_graph_mode(mode: str) -> None:
    os.environ["GRAPH_RAG_MODE"] = mode


def _run_matcher(question: str, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    from tools.matcher import match_exercises
    payload: Dict[str, Any] = overrides or {}
    payload.setdefault("query", question)
    return match_exercises(payload)


def _run_analytics(op: Dict[str, Any]) -> Dict[str, Any]:
    from tools.analytics import run as analytics_run
    return analytics_run(op)


def _run_vector(question: str) -> Dict[str, Any]:
    from tools.vector_rag import query as vq
    return vq(question)


def _run_graph(question: str) -> Dict[str, Any]:
    from tools.graph_rag import query as gq
    return gq(question)



with st.sidebar:
    st.header("Profil i dane")
    profiles = loaded.profiles or []
    if profiles:
        labels = []
        for i, p in enumerate(profiles):
            pid = p.get("id") or p.get("name") or f"profile_{i+1}"
            goal = p.get("goal", "?")
            labels.append(f"{pid} · {goal}")
        idx = st.selectbox("Profil", list(range(len(profiles))), format_func=lambda i: labels[i])
        active = profiles[idx]
        _persist_active_profile(active)
        st.caption("Wybrany profil zapisany jako data/input/profile.json")
    else:
        st.info("Brak profili w data/input (profiles.json/profile.json).")

    st.divider()
    st.subheader("Indeksy (opcjonalnie)")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Zbuduj indeks dokumentów"):
            from tools.vector_rag import ingest_docs
            out = ingest_docs("data/docs")
            st.success(f"OK: {out}")
    with c2:
        if st.button("Zbuduj graf lokalny"):
            from tools.graph_rag import ingest_edges_to_json
            out = ingest_edges_to_json()
            st.success(f"OK: {out}")

    st.divider()
    st.subheader("Graf (opcjonalnie)")
    graph_mode = st.radio("Źródło relacji", ["Local", "Neo4j"], horizontal=True)
    _set_graph_mode("neo4j" if graph_mode == "Neo4j" else "local")
    if graph_mode == "Neo4j":
        st.caption("Jeśli Neo4j nie działa na tym urządzeniu, zostaw Local.")
        if st.button("Sync edges.csv → Neo4j"):
            try:
                from tools.graph_rag import ingest_edges_to_neo4j
                msg = ingest_edges_to_neo4j("data/graph/edges.csv")
                st.success(msg)
            except Exception as e:
                st.error(str(e))


col_left, col_right = st.columns([2, 1], gap="large")

with col_left:
    task = st.radio(
        "Zadanie",
        ["Dopasowanie", "Analityka", "Scenariusz (What-if)", "Odpowiedź opisowa"],
        horizontal=True,
    )

    knowledge = st.radio(
        "Źródło wiedzy do uzasadnień",
        ["Auto (Agent)", "Dokumenty (Vector)", "Relacje (Graf)", "Porównanie"],
        horizontal=True,
    )

    st.divider()

    if task == "Analityka":
        st.caption("Wklej operację w JSON (count/filter/aggregate/diff).")
        op_text = st.text_area("Operacja JSON", height=140, value='{"op":"count","by":"tag"}')
        run = st.button("Uruchom", type="primary")
        if run:
            op = json.loads(op_text)
            res = _run_analytics(op)
            st.session_state["last_debug"] = {"task": task, "op": op, "result": res}
            st.subheader("Wynik")
            st.json(res)

    elif task == "Scenariusz (What-if)":
        st.caption("Symulacja zmian (np. brak sprzętu) i porównanie wyników.")
        base_q = st.text_area("Opis bazowy", height=90, value="Dobierz 3 ćwiczenia pod hipertrofię dla sprzętu dumbbell + bench, ograniczenie shoulder_pressing_pain.")
        whatif = st.text_area("Zmiana (what-if)", height=90, value="Usuń sprzęt: bench. Brak maszyn i kabli przez 7 dni.")
        run = st.button("Uruchom", type="primary")
        if run:
            base = _run_matcher(base_q, overrides={})

            removed = []
            txt = whatif.lower()
            if "bench" in txt or "ławk" in txt:
                removed.append("bench")
            if "machine" in txt or "maszyn" in txt:
                removed.append("machine")
            if "cable" in txt or "kabl" in txt:
                removed.append("cable")

            overrides = {"equipment_unavailable": removed, "query": base_q + " " + whatif}
            try:
                prof = json.load(open("data/input/profile.json", "r", encoding="utf-8"))
                eq = prof.get("equipment_available") or prof.get("equipment") or []
                eq2 = [e for e in eq if e not in removed]
                overrides["equipment"] = eq2
            except Exception:
                pass

            alt = _run_matcher(base_q, overrides=overrides)

            baseline_top = [x.get("id") for x in (base.get("top") or [])[:5] if x.get("id")]
            whatif_top = [x.get("id") for x in (alt.get("top") or [])[:5] if x.get("id")]
            bset, wset = set(baseline_top), set(whatif_top)
            diff = {
                "constraints_removed": removed,
                "baseline_top": baseline_top,
                "whatif_top": whatif_top,
                "removed": sorted(list(bset - wset)),
                "added": sorted(list(wset - bset)),
                "kept": sorted(list(bset & wset)),
            }
            st.session_state["last_debug"] = {"task": task, "baseline": base, "whatif": alt, "diff": diff}

            st.subheader("Porównanie")

            def _render_short_list(items: list[dict[str, Any]]):
                if not items:
                    st.info("Brak wyników.")
                    return
                for i, ex in enumerate(items[:5], start=1):
                    name = ex.get("name") or ex.get("id")
                    st.markdown(f"**{i}. {name}**")
                    reasons = ex.get("reasons") or []
                    if reasons:
                        st.caption(", ".join(reasons))
                    sb = ex.get("score_breakdown")
                    if isinstance(sb, dict):
                        st.caption("score: " + ", ".join([f"{k}={v}" for k, v in sb.items()]))

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### Bazowo")
                _render_short_list(base.get("top") or [])
            with c2:
                st.markdown("### What-if")
                _render_short_list(alt.get("top") or [])
            st.markdown("### Różnice")
            st.write(
                f"**Usunięte z top5:** {', '.join(diff['removed']) if diff['removed'] else '—'}\n\n"
                f"**Dodane do top5:** {', '.join(diff.get('added', [])) if diff.get('added') else '—'}\n\n"
                f"**Wspólne w top5:** {', '.join(diff.get('kept', [])) if diff.get('kept') else '—'}"
            )

    else:
        question = st.text_area("Pytanie", height=140)
        run = st.button("Uruchom", type="primary")

        if run and question.strip():
            q = question.strip()

            if task == "Dopasowanie":
                match = _run_matcher(q, overrides={})
                st.session_state["last_debug"] = {"task": task, "match": match}
                st.subheader("Rekomendacje")
                top = match.get("top") or []
                if top:
                    for i, ex in enumerate(top[:5], start=1):
                        st.markdown(f"**{i}. {ex.get('name')}**")
                        st.caption(", ".join(ex.get("reasons") or []))
                else:
                    st.info("Brak dopasowań.")

            else:
                if knowledge == "Auto (Agent)":
                    ans, dbg_trace = agent_full.run(q, knowledge_mode="auto")
                    st.session_state["last_debug"] = {"task": task, "knowledge": knowledge, "agent_trace": dbg_trace}
                    st.subheader("Odpowiedź")
                    st.write(ans)

                elif knowledge == "Dokumenty (Vector)":

                    obs = _run_vector(q)
                    ctx_items = obs.get("items") or []
                    ctx = "\n\n".join(
                        [f"[source:{(it.get('meta') or {}).get('source','?')}] {(it.get('text') or '')[:700]}" for it in ctx_items[:5]]
                    )
                    prompt = (
                        "Odpowiedz krótko i konkretnie. Opieraj się na KONTEKŚCIE. "
                        "Jeśli kontekst jest ubogi, powiedz czego brakuje.\n\n"
                        f"KONTEKST:\n{ctx}\n\nPYTANIE:\n{q}"
                    )
                    ans = llm.generate("Jesteś asystentem treningowym.", prompt).text
                    st.session_state["last_debug"] = {"task": task, "knowledge": knowledge, "vector": obs}
                    st.subheader("Odpowiedź")
                    st.write(ans)

                elif knowledge == "Relacje (Graf)":
                    ql = q.lower()
                    wants_count = any(k in ql for k in ["policz", "zlicz", "ile ", "ile ", "ile ćwicze", "ile cwicze"]) and "ćwic" in ql
                    if wants_count and ("hantl" in ql or "dumbbell" in ql) and ("ławk" in ql or "bench" in ql):
                        from tools.graph_rag import count_exercises_with_equipment

                        allowed = []
                        if "hantl" in ql or "dumbbell" in ql:
                            allowed.append("dumbbell")
                        if "ławk" in ql or "bench" in ql:
                            allowed.append("bench")

                        out = count_exercises_with_equipment(allowed, exact=False)
                        count = out.get("count", 0)
                        ex = out.get("examples") or []
                        st.subheader("Odpowiedź")
                        st.write(f"W grafie znalazłem **{count}** ćwiczeń możliwych do wykonania używając wyłącznie: {', '.join(allowed)} (lub ich podzbioru).")
                        if ex:
                            st.caption("Przykłady:")
                            st.write(", ".join(ex))
                        st.session_state["last_debug"] = {"task": task, "knowledge": knowledge, "graph": out}
                    else:
                        obs = _run_graph(q)
                        edges = obs.get("edges") or []
                        rels = "\n".join([f"{e.get('source')} -[{e.get('relation')}]-> {e.get('target')}" for e in edges[:30]])
                        prompt = (
                            "Odpowiedz krótko i konkretnie. Opieraj się na RELACJACH. "
                            "Jeśli relacji jest mało, powiedz czego brakuje w grafie.\n\n"
                            f"RELACJE:\n{rels}\n\nPYTANIE:\n{q}"
                        )
                        ans = llm.generate("Jesteś asystentem treningowym.", prompt).text
                        st.session_state["last_debug"] = {"task": task, "knowledge": knowledge, "graph": obs}
                        st.subheader("Odpowiedź")
                        st.write(ans)

                else:
                    va = _run_vector(q)
                    ga = _run_graph(q)

                    vctx_items = va.get("items") or []
                    vctx = "\n\n".join([f"[source:{(it.get('meta') or {}).get('source','?')}] {(it.get('text') or '')[:600]}" for it in vctx_items[:4]])
                    gedges = ga.get("edges") or []
                    grels = "\n".join([f"{e.get('source')} -[{e.get('relation')}]-> {e.get('target')}" for e in gedges[:25]])

                    v_ans = llm.generate("Jesteś asystentem treningowym.", f"KONTEKST:\n{vctx}\n\nPYTANIE:\n{q}").text
                    g_ans = llm.generate("Jesteś asystentem treningowym.", f"RELACJE:\n{grels}\n\nPYTANIE:\n{q}").text

                    st.subheader("Porównanie")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("### Dokumenty (Vector)")
                        st.write(v_ans)
                    with c2:
                        st.markdown("### Relacje (Graf)")
                        st.write(g_ans)

                    summary = llm.generate(
                        "Jesteś recenzentem.",
                        f"Porównaj krótko dwie odpowiedzi (jakość, ograniczenia, kiedy lepsza).\n\nVector:\n{v_ans}\n\nGraph:\n{g_ans}",
                    ).text
                    st.markdown("### Podsumowanie")
                    st.write(summary)
                    st.session_state["last_debug"] = {"task": task, "knowledge": knowledge, "vector": va, "graph": ga, "summary": summary}


with col_right:
    st.markdown("### Źródła i szczegóły")
    tab_src, tab_run = st.tabs(["Źródła (raw)", "Przebieg"])

    dbg = st.session_state.get("last_debug")

    with tab_src:
        if not dbg:
            st.caption("Uruchom zapytanie — tutaj pojawią się zwrócone źródła i dane pomocnicze.")
        else:
            st.json(dbg, expanded=False)

    with tab_run:
        if not dbg:
            st.caption("Brak przebiegu — najpierw uruchom zapytanie.")
        else:
            task = dbg.get("task", "")
            knowledge = dbg.get("knowledge", "")
            st.markdown(f"**Zadanie:** {task}")
            st.markdown(f"**Źródło wiedzy:** {knowledge}")

            v = dbg.get("vector") or {}
            items = v.get("items") or []
            if items:
                st.markdown("**Dokumenty użyte do uzasadnień:**")
                for it in items[:10]:
                    src = (it.get("meta") or {}).get("source") or it.get("id")
                    dist = it.get("distance")
                    if dist is None:
                        st.write(f"- {src}")
                    else:
                        st.write(f"- {src} (score: {dist:.3f})")

            g = dbg.get("graph") or {}
            edges = g.get("edges") or []
            if edges:
                st.markdown("**Relacje grafu (przykładowe):**")
                for e in edges[:10]:
                    st.write(f"- {e.get('source')} → {e.get('relation')} → {e.get('target')}")

            if dbg.get("what_if"):
                st.markdown("**Scenariusz (what‑if):**")
                st.json(dbg.get("what_if"), expanded=False)
