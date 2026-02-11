# Graf wiedzy – schemat (lokalny)

Graf wiedzy łączy ćwiczenia ze sprzętem, mięśniami i ograniczeniami.

## Węzły

- `EX:<id>` – ćwiczenie (ID z `data/catalog/exercises.json`)
- `EQ:<name>` – sprzęt (np. `EQ:dumbbell`, `EQ:bench`)
- `M:<name>` – mięsień (np. `M:Chest`)
- `TAG:<name>` – tag (np. `TAG:hypertrophy`)
- `LIM:<name>` – ograniczenie (np. `LIM:shoulder_pressing_pain`)

## Relacje

- `requires` – ćwiczenie wymaga sprzętu
- `targets` – ćwiczenie celuje w mięsień
- `tag` – opis cech ćwiczenia
- `contraindicated_for` – ćwiczenie niezalecane przy danym ograniczeniu

## Budowa grafu

Aplikacja ładuje `data/graph/graph.json`.
Jeśli graf jest niepełny, kod automatycznie uzupełnia relacje na podstawie katalogu ćwiczeń.
- `requires` – ćwiczenie wymaga sprzętu
- `targets` – ćwiczenie trafia w mięsień
- `tag` – cechy ćwiczenia
- `contraindicated_for` – ograniczenia/urazy

## Jak powstaje graf

- `data/graph/graph.json` może zawierać relacje wyekstrahowane z dokumentów.
- Jeśli ten plik jest niepełny, kod automatycznie uzupełnia graf na podstawie `data/catalog/exercises.json`.

