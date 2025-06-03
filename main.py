from xml_parser import extract_990_data
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import json
from openai import OpenAI
from pdfminer.high_level import extract_text
from pdf_parser import extract_functional_expenses
from pdf_parser import extract_key_sections

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

CORS(app, resources={r"/api/*": {"origins": [
    "https://traceport-next-ui.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001"
]}})

client = OpenAI()

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Upload Endpoint ---
@app.route('/api/upload-docs', methods=['POST'])
def upload_docs():
    try:
        for f in ['form990.pdf', 'annual_report.pdf']:
            f_path = os.path.join(UPLOAD_FOLDER, f)
            if os.path.exists(f_path):
                os.remove(f_path)

        form990 = request.files.get('form990')
        annual_report = request.files.get('annualReport')

        if not form990:
            return jsonify({'error': 'Form 990 is required'}), 400

        form990.save(os.path.join(UPLOAD_FOLDER, 'form990.pdf'))
        if annual_report:
            annual_report.save(os.path.join(UPLOAD_FOLDER, 'annual_report.pdf'))

        return jsonify({'status': 'Files uploaded successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Functional Expense Analysis ---
@app.route('/api/analyze', methods=['POST'])
def analyze_api():
    pdf_path = os.path.join(UPLOAD_FOLDER, 'form990.pdf')
    if not os.path.exists(pdf_path):
        return jsonify({"error": "No uploaded file found"}), 400

    totals = extract_functional_expenses(pdf_path)
    if totals:
        return jsonify(totals)
    return jsonify({"error": "Could not extract data"}), 422

# --- Program Suggestion Endpoint ---
@app.route('/api/suggest-programs', methods=['POST'])
def suggest_programs():
    try:
        mode = request.headers.get("X-Upload-Mode", "pdf")

        if mode == "xml":
            # Get parsed XML data stored earlier
            xml_data_path = os.path.join(UPLOAD_FOLDER, 'xml_data.json')
            if os.path.exists(xml_data_path):
                with open(xml_data_path, 'r') as f:
                    xml_data = json.load(f)
                form990_text = xml_data.get("raw_text", "")[:5000]
                annual_text = ""

                print("🪵 XML mode: sending to OpenAI")
                print("📄 form990_text preview:\n", form990_text[:1000])
            else:
                return jsonify({"error": "No XML data found. Please upload XML first."}), 400
        else:
            # Default: load PDF text
            form990_path = os.path.join(UPLOAD_FOLDER, 'form990.pdf')
            annual_path = os.path.join(UPLOAD_FOLDER, 'annual_report.pdf')

            form990_text = extract_key_sections(form990_path) if os.path.exists(form990_path) else ""
            annual_text = extract_text(annual_path)[:5000] if os.path.exists(annual_path) else ""

        # Prompt for OpenAI
        prompt = f"""
        You are reviewing a nonprofit's IRS Form 990 and optional annual report. Your job is to identify 3 to 5 specific program areas that the nonprofit operates.

        ONLY return a JSON array like this:
        [
        {{
            "name": "Program Name",
            "description": "Short summary of what the program does."
        }}
        ]

        If you cannot find clear evidence of at least one real program, return this exact JSON:
        [
        {{
            "name": "Could not extract programs",
            "description": "The provided documents did not include any identifiable program descriptions."
        }}
        ]

        Do NOT guess. Base your answer only on the content below.

        Form 990:
        {form990_text}

        Annual Report:
        {annual_text}
        """

        print("=== Prompt sent to OpenAI ===")
        print(prompt)
        print("=== End of Prompt ===")
        print("📤 Sending request to OpenAI...")
        print("📝 Prompt length:", len(prompt))

        # Safe OpenAI call
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a nonprofit program classifier."},
                    {"role": "user", "content": prompt}
                ]
            )
        except Exception as e:
            print("❗ Error calling OpenAI:", e)
            return jsonify({"error": f"OpenAI API call failed: {str(e)}"}), 500

        content = response.choices[0].message.content.strip()
        print("🧠 OpenAI raw response:", content)
        print("🧠 Type of content:", type(content))

        try:
            suggestions = json.loads(content)
            return jsonify(suggestions)
        except json.JSONDecodeError:
            import re
            matches = re.findall(r'\{[^{}]+\}', content)
            if matches:
                try:
                    suggestions = [json.loads(m) for m in matches]
                    return jsonify(suggestions)
                except Exception:
                    pass

            return jsonify({
                "message": "The AI could not detect clear program areas from the uploaded document.",
                "raw_response": content
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- Program Allocation ---
@app.route('/api/program-allocation', methods=['POST'])
def program_allocation():
    data = request.get_json()
    if not data or 'programs' not in data:
        return jsonify({"error": "Invalid input format"}), 400

    programs = data['programs']
    total_pct = sum(float(p.get('percentage', 0)) for p in programs)

    if abs(total_pct - 100) > 1:
        return jsonify({"error": f"Program percentages must total ~100%. Currently: {total_pct}"}), 422

    return jsonify({
        "status": "Program allocation received",
        "programs": programs,
        "total_pct": total_pct
    })

@app.route('/api/xml-analyze', methods=['POST'])
def process_xml():
    print("🔍 Received request at /api/xml-analyze")
    data = request.get_json()
    xml_url = data.get("xml_url")

    if not xml_url:
        return jsonify({"error": "No XML URL provided"}), 400

    try:
        result = extract_990_data(xml_url)

        # Combine mission, short programs, and schedule O into one big blob of text
        result["raw_text"] = "\n\n".join(result.get("mission_fields", []))
        result["raw_text"] += "\n\n" + "\n\n".join(p["short"] for p in result.get("short_programs", []) if p.get("short"))
        result["raw_text"] += "\n\n" + result.get("schedule_o", "")

        # Save raw XML data to a file for later use
        with open(os.path.join(UPLOAD_FOLDER, 'xml_data.json'), 'w') as f:
            json.dump(result, f)

        expenses = result.get("functional_expenses", {})
        program = expenses.get("program_expenses", 0)
        admin = expenses.get("management_expenses", 0)
        fundraising = expenses.get("fundraising_expenses", 0)
        total = program + admin + fundraising or 1

        return jsonify({
            "program": program,
            "admin": admin,
            "fundraising": fundraising,
            "program_pct": round(100 * program / total),
            "admin_pct": round(100 * admin / total),
            "fundraising_pct": round(100 * fundraising / total),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Run App ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)