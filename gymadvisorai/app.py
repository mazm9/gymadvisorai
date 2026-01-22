from gymadvisorai.graph.in_memory import load_state, total_tonnage_for_exercise

def main():
    state = load_state()
    print("User:", state["user_id"])
    print("Exercises:", len(state["ex"]))
    print("Sessions:", len(state["sessions"]))
    print("Bench Press tonnage:", total_tonnage_for_exercise(state, "Bench Press"))

if __name__ == "__main__":
    main()
