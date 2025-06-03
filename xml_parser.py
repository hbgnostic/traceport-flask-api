import requests
import xml.etree.ElementTree as ET
import json

def extract_990_data(xml_url):
    response = requests.get(xml_url)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ns = {"irs": "http://www.irs.gov/efile"}

    expenses = get_functional_expenses(root, ns)

    mission_fields = []
    for tag in ["ActivityOrMissionDesc", "MissionDesc", "Desc"]:
        for elem in root.findall(f".//irs:{tag}", ns):
            if elem is not None and elem.text and elem.text.strip():
                mission_fields.append(elem.text.strip())

    short_programs = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag.startswith("ProgSrvcAccomActy") and "Grp" in tag:
            desc = elem.find(".//irs:Desc", ns)
            amt = elem.find(".//irs:ExpenseAmt", ns)
            if desc is not None and desc.text:
                short_programs.append({
                    "short": desc.text.strip(),
                    "expenses": int(amt.text.strip()) if amt is not None and amt.text and amt.text.strip().isdigit() else None
                })

    schedule_o = []
    for entry in root.findall(".//irs:IRS990ScheduleO", ns):
        for txt in entry.findall(".//irs:ExplanationTxt", ns):
            if txt is not None and txt.text:
                schedule_o.append(txt.text.strip())
    schedule_o_text = "\n\n".join(schedule_o)

    # 📝 Save combined text to file for suggestions later
    combined_text = "\n\n".join(mission_fields)
    combined_text += "\n\n" + "\n\n".join(p["short"] for p in short_programs if p.get("short"))
    combined_text += "\n\n" + schedule_o_text

    with open("uploads/xml_data.json", "w") as f:
        json.dump({ "raw_text": combined_text }, f)

    return {
        "functional_expenses": expenses,
        "mission_fields": mission_fields,
        "short_programs": short_programs,
        "schedule_o": schedule_o_text
    }

def get_functional_expenses(root, ns):
    def extract_amt(el):
        return int(el.text.strip()) if el is not None and el.text and el.text.strip().isdigit() else 0

    grp = root.find(".//irs:TotalFunctionalExpensesGrp", ns)
    if grp is not None:
        return {
            "program_expenses": extract_amt(grp.find("irs:ProgramServicesAmt", ns)),
            "management_expenses": extract_amt(grp.find("irs:ManagementAndGeneralAmt", ns)),
            "fundraising_expenses": extract_amt(grp.find("irs:FundraisingAmt", ns))
        }

    def get_first_match(tags):
        for tag in tags:
            el = root.find(f".//irs:{tag}", ns)
            if el is not None and el.text and el.text.strip().isdigit():
                return int(el.text.strip())
        return 0

    return {
        "program_expenses": get_first_match(["TotalProgramServiceExpensesAmt", "ProgramServicesAmt"]),
        "management_expenses": get_first_match(["ManagementAndGeneralExpensesAmt", "ManagementAndGeneralAmt"]),
        "fundraising_expenses": get_first_match(["FundraisingExpensesAmt", "FundraisingAmt"])
    }