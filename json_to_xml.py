import json
import os
import sys
from openpyxl import Workbook

# Zaktualizowana kolejność kolumn - dodano 'title'
FIELD_ORDER = ['name', 'title', 'current_company', 'location', 'profile_url']

def json_to_xlsx(json_filename):
    if not os.path.exists(json_filename):
        print(f"❌ Plik '{json_filename}' nie istnieje.")
        return

    base_name = os.path.splitext(json_filename)[0]
    xlsx_filename = base_name + '.xlsx'

    # Wczytanie danych JSON
    try:
        with open(json_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Błąd wczytywania JSON: {e}")
        return

    if not isinstance(data, list):
        print("❌ Nieprawidłowa struktura JSON – oczekiwana lista obiektów.")
        return

    # Tworzenie pliku Excel
    wb = Workbook()
    ws = wb.active
    ws.title = 'Data'

    # Nagłówki
    ws.append(FIELD_ORDER)

    # Wiersze danych
    for item in data:
        row = [item.get(field, "") for field in FIELD_ORDER]
        ws.append(row)

    wb.save(xlsx_filename)
    print(f"✅ Zapisano do pliku: {xlsx_filename}")

# --- ENTRY POINT ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Użycie: python json_to_xlsx.py <nazwa_pliku.json>")
    else:
        json_to_xlsx(sys.argv[1])