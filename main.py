from flask import Flask, render_template, request, jsonify
import pdfplumber

app = Flask(__name__)

# 🧠 Function to extract functional expenses
def extract_functional_expenses(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and ("Functional Expenses" in text or "Part IX" in text or "Line 25" in text):
                    print(f"🔍 Trying to extract from page {i + 1}")
                    print("📄 Page preview:\n", text[:500])
                    table = page.extract_table()
                    print("🧾 Raw extracted table:\n", table)

                    if not table:
                        continue

                    for row in reversed(table):
                        if not row:
                            continue

                        numeric_values = []
                        for cell in row:
                            if cell:
                                cleaned = cell.replace(",", "").replace(".", "").strip()
                                if cleaned.isdigit():
                                    value = int(cleaned)
                                    if value > 50000:
                                        numeric_values.append(value)

                        if len(numeric_values) >= 3:
                            total, program, admin = numeric_values[:3]
                            fundraising = total - (program + admin)

                            return {
                                "program": program,
                                "admin": admin,
                                "fundraising": fundraising,
                                "program_pct": round(program / total * 100, 1),
                                "admin_pct": round(admin / total * 100, 1),
                                "fundraising_pct": round(fundraising / total * 100, 1)
                            }

        return None
    except Exception as e:
        print("ERROR:", e)
        return None

# 🖥️ Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    uploaded_file = request.files['file']
    if uploaded_file and uploaded_file.filename.endswith('.pdf'):
        pdf_path = "uploaded_990.pdf"
        uploaded_file.save(pdf_path)
        totals = extract_functional_expenses(pdf_path)
        if totals:
            return jsonify(totals)
        return jsonify({"error": "Could not extract data"}), 422
    return jsonify({"error": "Invalid file"}), 400

@app.route('/confirm', methods=['POST'])
def confirm():
    return jsonify({"status": "Functional allocation confirmed (placeholder)"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)