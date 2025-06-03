# pdf_parser.py

import pdfplumber
import re

# --- Existing: Extract Functional Expense Breakdown ---
def extract_functional_expenses(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and ("Functional Expenses" in text or "Part IX" in text or "Line 25" in text):
                    table = page.extract_table()
                    if not table:
                        continue

                    for row in reversed(table):
                        if not row:
                            continue
                        numeric_values = [
                            int(re.sub(r"[^\d]", "", cell))
                            for cell in row if cell and re.sub(r"[^\d]", "", cell).isdigit()
                        ]

                        if len(numeric_values) >= 3:
                            numeric_values.sort(reverse=True)
                            total = numeric_values[0]
                            program = numeric_values[1]
                            admin = numeric_values[2]
                            fundraising = total - (program + admin)

                            if fundraising >= 0 and total > 10000:
                                return {
                                    "program": program,
                                    "admin": admin,
                                    "fundraising": fundraising,
                                    "program_pct": round(program / total * 100, 1),
                                    "admin_pct": round(admin / total * 100, 1),
                                    "fundraising_pct": round(fundraising / total * 100, 1),
                                    "total": total
                                }
        return None
    except Exception as e:
        print("❗ ERROR in extract_functional_expenses:", e)
        return None

# --- ✅ NEW: Extract Key Narrative Sections for GPT ---
def extract_key_sections(pdf_path, max_chars=10000):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            mission_text = ""
            part_iii_text = ""
            schedule_o_text = ""

            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                # Mission section
                if "organization’s mission" in text.lower() and not mission_text:
                    mission_text = text.strip()

                # Part III – Program Accomplishments
                if "part iii" in text.lower() and "program service accomplishments" in text.lower():
                    part_iii_text += "\n" + text.strip()

                # Schedule O
                if "schedule o" in text.lower():
                    schedule_o_text += "\n" + text.strip()

        combined = "\n\n=== Mission Section ===\n" + mission_text
        combined += "\n\n=== Part III: Program Accomplishments ===\n" + part_iii_text

        # Only include Schedule O if it's not just repeating Part III
        if schedule_o_text.strip() != part_iii_text.strip():
            combined += "\n\n=== Schedule O ===\n" + schedule_o_text

        return combined[:max_chars]
    except Exception as e:
        print("❗ ERROR in extract_key_sections:", e)
        return ""

