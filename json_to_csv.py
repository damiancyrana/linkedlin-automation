"""
uzycie 
python3 json_to_csv.py <nazwa_pliku.json>
"""
import json
import csv
import os
import sys

def json_to_csv(json_filename):
    # Sprawdź czy plik istnieje
    if not os.path.exists(json_filename):
        print(f"❌ Plik '{json_filename}' nie istnieje.")
        return

    # Wygeneruj nazwę pliku CSV
    base_name = os.path.splitext(json_filename)[0]
    csv_filename = base_name + '.csv'

    # Wczytaj dane z pliku JSON
    try:
        with open(json_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Błąd wczytywania JSON: {e}")
        return

    # Zapisz do pliku CSV
    if isinstance(data, list) and data:
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"✅ Zapisano do pliku: {csv_filename}")
    else:
        print("⚠️ Plik JSON jest pusty lub ma niepoprawną strukturę.")

# --- ENTRY POINT ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Użycie: python json_to_csv.py <nazwa_pliku.json>")
    else:
        json_to_csv(sys.argv[1])
