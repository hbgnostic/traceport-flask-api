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
import hashlib
import re
from datetime import datetime
from meta_tag_scanner import MetaTagEngine

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

CORS(app, resources={r"/api/*": {"origins": [
    "https://traceport-next-ui.vercel.app",
    "https://traceport-next-ui-git-main-bridget-dorans-projects.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001"
]}})

client = OpenAI()

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize MetaTagEngine
META_TAG_CSV_PATH = 'docs/Traceport Crosswalk NTEE Groups.csv'
meta_tag_engine = None

try:
    meta_tag_engine = MetaTagEngine(META_TAG_CSV_PATH, max_tags=3, min_confidence=0.1)
    print("✅ MetaTagEngine initialized successfully")
except Exception as e:
    print(f"⚠️ Failed to initialize MetaTagEngine: {e}")
    print("📝 Will use fallback meta tag generation")

# Helper functions for new JSON format
def generate_program_id(program_name):
    """Generate a consistent program ID from program name"""
    clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', program_name.lower())
    hash_part = hashlib.md5(clean_name.encode()).hexdigest()[:6]
    return f"prog_{hash_part}"

def extract_meta_tags(program_description):
    """Extract meta tags from program description using MetaTagEngine or fallback"""
    global meta_tag_engine

    # Use MetaTagEngine if available
    if meta_tag_engine:
        try:
            return meta_tag_engine.scan_program(program_description)
        except Exception as e:
            print(f"⚠️ MetaTagEngine error: {e}")
            # Fall through to fallback logic

    # Fallback to original keyword matching
    keywords_map = {
        'education': ['education', 'school', 'learning', 'academic', 'curriculum', 'teaching'],
        'literacy': ['literacy', 'reading', 'writing', 'books', 'literature'],
        'youth': ['youth', 'children', 'kids', 'teen', 'adolescent', 'young'],
        'science': ['science', 'stem', 'research', 'laboratory', 'scientific'],
        'technology': ['technology', 'tech', 'computer', 'digital', 'software'],
        'students': ['student', 'pupil', 'learner', 'scholar'],
        'mentorship': ['mentor', 'guidance', 'counseling', 'coaching', 'support'],
        'health': ['health', 'medical', 'wellness', 'healthcare', 'medicine'],
        'community': ['community', 'neighborhood', 'local', 'civic', 'public'],
        'environment': ['environment', 'green', 'sustainability', 'climate', 'conservation'],
        'arts': ['arts', 'creative', 'cultural', 'music', 'theater', 'dance'],
        'sports': ['sports', 'athletic', 'fitness', 'recreation', 'physical']
    }

    description_lower = program_description.lower()
    tags = []

    for tag, keywords in keywords_map.items():
        if any(keyword in description_lower for keyword in keywords):
            tags.append(tag)

    return tags[:3] if tags else ["community"]  # Limit to 3 tags with fallback

def create_functional_allocation_response(result):
    """Transform XML data to functional allocation format"""
    expenses = result.get("functional_expenses", {})
    program = expenses.get("program_expenses", 0)
    admin = expenses.get("management_expenses", 0)
    fundraising = expenses.get("fundraising_expenses", 0)
    total = program + admin + fundraising or 1

    # Get tax year from transparency metrics
    transparency = result.get("transparency_metrics", {})
    tax_year = transparency.get("tax_year", datetime.now().year)
    fiscal_year_start = f"{tax_year}-01-01"

    # Create program breakdown from multiple sources
    program_breakdown = []
    short_programs = result.get("short_programs", [])

    if short_programs:
        # Use short_programs if available
        total_program_expenses = sum(p.get("expenses", 0) for p in short_programs if p.get("expenses"))

        for i, program_info in enumerate(short_programs):
            if program_info.get("short"):
                program_name = program_info["short"][:50]  # Truncate long names
                program_expenses = program_info.get("expenses", 0)

                # Calculate percentage of total program expenses
                if total_program_expenses > 0:
                    percentage = round((program_expenses / total_program_expenses) * 100)
                else:
                    percentage = round(100 / len(short_programs))  # Equal distribution

                program_breakdown.append({
                    "programId": generate_program_id(program_name),
                    "programName": program_name,
                    "percentageOfProgram": percentage,
                    "metaTags": extract_meta_tags(program_name)
                })

    # If no short_programs, try to extract from mission fields
    elif result.get("mission_fields"):
        mission_fields = result.get("mission_fields", [])

        # Filter mission fields to find actual program descriptions
        program_descriptions = []
        seen_descriptions = set()
        for field in mission_fields:
            if field and len(field.strip()) > 20:  # Skip short/incomplete entries
                # Skip obvious non-program entries
                skip_keywords = ['income', 'revenue', 'reimbursements', 'subscriptions', 'telephone', 'lease', 'misc']
                if not any(keyword in field.lower() for keyword in skip_keywords):
                    # Avoid duplicates
                    field_clean = field.strip().lower()
                    if field_clean not in seen_descriptions:
                        seen_descriptions.add(field_clean)
                        program_descriptions.append(field.strip())

        if program_descriptions:
            # Create programs from mission field descriptions
            for i, description in enumerate(program_descriptions[:4]):  # Limit to 4 programs
                # Create a shorter program name from the description
                program_name = description[:60].strip()
                if program_name.endswith('.'):
                    program_name = program_name[:-1]

                # Distribute percentages equally among programs
                percentage = round(100 / len(program_descriptions))

                program_breakdown.append({
                    "programId": generate_program_id(program_name),
                    "programName": program_name,
                    "percentageOfProgram": percentage,
                    "metaTags": extract_meta_tags(program_name)
                })

    # If still no programs found, create a default one
    if not program_breakdown:
        program_breakdown = [{
            "programId": "prog_default",
            "programName": "General Programs",
            "percentageOfProgram": 100,
            "metaTags": ["community"]
        }]

    return {
        "fiscalYearStart": fiscal_year_start,
        "functionalAllocation": {
            "program": round(100 * program / total),
            "admin": round(100 * admin / total),
            "fundraising": round(100 * fundraising / total)
        },
        "programBreakdown": program_breakdown
    }

def create_transparency_metrics_response(result):
    """Transform XML data to transparency metrics format"""
    transparency = result.get("transparency_metrics", {})

    return {
        "source": transparency.get("source", "xml"),
        "data_quality": transparency.get("data_quality", "complete"),
        "last_updated": transparency.get("last_updated", datetime.now().isoformat()),
        "transparency": {
            "website_url": transparency.get("website_url", ""),
            "has_website": transparency.get("has_website", False)
        },
        "governance": {
            "board_size": transparency.get("board_size", 0),
            "independent_members": transparency.get("independent_members", 0),
            "governance_rating": transparency.get("governance_rating", "unknown"),
            "has_conflict_policy": transparency.get("has_conflict_policy", False),
            "has_whistleblower_policy": transparency.get("has_whistleblower_policy", False),
            "has_retention_policy": transparency.get("has_retention_policy", False)
        },
        "tax_year": transparency.get("tax_year", 0),
        "filing_date": transparency.get("filing_date", ""),
        "filing_status": transparency.get("filing_status", "unknown"),
        "financial_health": {
            "total_revenue": transparency.get("total_revenue", 0),
            "total_expenses": transparency.get("total_expenses", 0),
            "net_assets": transparency.get("net_assets", 0),
            "program_ratio": transparency.get("program_ratio", 0),
            "admin_ratio": transparency.get("admin_ratio", 0),
            "fundraising_ratio": transparency.get("fundraising_ratio", 0)
        }
    }

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

# --- UPDATED: XML Analysis with New Format ---
@app.route('/api/xml-analyze', methods=['POST'])
def process_xml():
    print("🔍 Received request at /api/xml-analyze")
    data = request.get_json()
    xml_url = data.get("xml_url")

    if not xml_url:
        return jsonify({"error": "No XML URL provided"}), 400

    try:
        print(f"📄 Processing XML URL: {xml_url[:100]}...")
        result = extract_990_data(xml_url)
        print("✅ XML processing completed successfully")

        # Combine mission, short programs, and schedule O into one big blob of text
        result["raw_text"] = "\n\n".join(result.get("mission_fields", []))
        result["raw_text"] += "\n\n" + "\n\n".join(p["short"] for p in result.get("short_programs", []) if p.get("short"))
        result["raw_text"] += "\n\n" + result.get("schedule_o", "")

        # Save raw XML data to a file for later use
        with open(os.path.join(UPLOAD_FOLDER, 'xml_data.json'), 'w') as f:
            json.dump(result, f)

        # Create the two new response formats
        functional_allocation = create_functional_allocation_response(result)
        transparency_metrics = create_transparency_metrics_response(result)

        print("🌟 New format responses created:")
        print(f"   Fiscal Year: {functional_allocation['fiscalYearStart']}")
        print(f"   Program Breakdown: {len(functional_allocation['programBreakdown'])} programs")
        print(f"   Governance Rating: {transparency_metrics['governance']['governance_rating']}")

        # Return the new two-blob format
        response_data = {
            "functionalAllocation": functional_allocation,
            "transparencyMetrics": transparency_metrics
        }

        print("📊 Final response prepared with new format")
        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Error processing XML: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- Run App ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)