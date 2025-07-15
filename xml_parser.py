import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime
import re

def extract_990_data(xml_url):
    response = requests.get(xml_url)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    ns = {"irs": "http://www.irs.gov/efile"}

    # Existing functionality
    expenses = get_functional_expenses(root, ns)
    
    # NEW: Extract transparency metrics
    transparency_metrics = extract_transparency_metrics(root, ns, expenses)

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

    # Save combined text to file for suggestions later
    combined_text = "\n\n".join(mission_fields)
    combined_text += "\n\n" + "\n\n".join(p["short"] for p in short_programs if p.get("short"))
    combined_text += "\n\n" + schedule_o_text

    with open("uploads/xml_data.json", "w") as f:
        json.dump({ "raw_text": combined_text }, f)

    return {
        "functional_expenses": expenses,
        "transparency_metrics": transparency_metrics,  # NEW
        "mission_fields": mission_fields,
        "short_programs": short_programs,
        "schedule_o": schedule_o_text
    }

def extract_transparency_metrics(root, ns, expenses):
    """Extract comprehensive transparency metrics from 990 XML"""
    
    def safe_extract_text(xpath_list, default=None):
        """Try multiple xpaths and return first non-empty result"""
        for xpath in xpath_list:
            elem = root.find(xpath, ns)
            if elem is not None and elem.text and elem.text.strip():
                return elem.text.strip()
        return default
    
    def safe_extract_int(xpath_list, default=0):
        """Extract integer value, return 0 if not found"""
        text = safe_extract_text(xpath_list)
        if text and text.replace(',', '').replace('$', '').isdigit():
            return int(text.replace(',', '').replace('$', ''))
        return default
    
    def safe_extract_bool(xpath_list, default=False):
        """Extract boolean value from Yes/No or 1/0"""
        text = safe_extract_text(xpath_list)
        if text:
            return text.lower() in ['yes', 'true', '1']
        return default

    # Filing Information
    tax_year = safe_extract_text([
        ".//irs:TaxYr",
        ".//irs:TaxYear", 
        ".//irs:PeriodBeginDt",
        ".//irs:TaxPeriodBeginDt"
    ])
    
    # Extract year from date if full date provided
    if tax_year and len(tax_year) > 4:
        tax_year = tax_year[:4]
    
    filing_date = safe_extract_text([
        ".//irs:SignatureDt",
        ".//irs:DateSigned"
    ])

    # Financial Health Metrics
    total_revenue = safe_extract_int([
        ".//irs:TotalRevenueAmt",
        ".//irs:TotalRevenue",
        ".//irs:CYTotalRevenueAmt"
    ])
    
    total_expenses = safe_extract_int([
        ".//irs:TotalExpensesAmt", 
        ".//irs:TotalExpenses",
        ".//irs:CYTotalExpensesAmt"
    ])
    
    net_assets = safe_extract_int([
        ".//irs:NetAssetsOrFundBalancesEOYAmt",
        ".//irs:TotalNetAssetsFundBalanceEOYAmt"
    ])

    # Governance Information
    voting_members = safe_extract_int([
        ".//irs:VotingMembersGoverningBodyCnt",
        ".//irs:NbrVotingMembersGoverningBody"
    ])
    
    independent_members = safe_extract_int([
        ".//irs:VotingMembersIndependentCnt", 
        ".//irs:NbrIndependentVotingMembers"
    ])

    # Website and Contact Info
    website = safe_extract_text([
        ".//irs:WebsiteAddressTxt",
        ".//irs:WebSite",
        ".//irs:BusinessWebsite"
    ])
    
    # Clean up website URL
    if website:
        if not website.startswith(('http://', 'https://')):
            website = 'https://' + website

    # Governance Policies
    conflict_policy = safe_extract_bool([
        ".//irs:ConflictOfInterestPolicyInd",
        ".//irs:ConflictOfInterestPolicy"
    ])
    
    whistleblower_policy = safe_extract_bool([
        ".//irs:WhistleblowerPolicyInd",
        ".//irs:WhistleblowerPolicy"
    ])
    
    document_retention_policy = safe_extract_bool([
        ".//irs:DocumentRetentionPolicyInd",
        ".//irs:DocumentRetentionPolicy"
    ])

    # Calculate ratios from functional expenses
    program_expenses = expenses.get("program_expenses", 0)
    management_expenses = expenses.get("management_expenses", 0) 
    fundraising_expenses = expenses.get("fundraising_expenses", 0)
    
    total_functional = program_expenses + management_expenses + fundraising_expenses
    
    program_ratio = round((program_expenses / total_functional * 100), 1) if total_functional > 0 else 0
    admin_ratio = round((management_expenses / total_functional * 100), 1) if total_functional > 0 else 0
    fundraising_ratio = round((fundraising_expenses / total_functional * 100), 1) if total_functional > 0 else 0

    # Determine filing status (simplified - would need more logic for real determination)
    filing_status = "unknown"
    if filing_date:
        # Basic heuristic - if filed, assume on time (would need deadline logic for accuracy)
        filing_status = "on_time"

    # Calculate governance score
    governance_indicators = [
        conflict_policy,
        whistleblower_policy, 
        document_retention_policy,
        voting_members >= 3,  # Minimum viable board
        independent_members > voting_members * 0.5 if voting_members > 0 else False  # Majority independent
    ]
    governance_score = sum(governance_indicators)
    
    if governance_score >= 4:
        governance_rating = "strong"
    elif governance_score >= 2:
        governance_rating = "good" 
    else:
        governance_rating = "needs_improvement"

    return {
        "source": "xml",
        "data_quality": "complete",
        "last_updated": datetime.now().isoformat(),
        
        # Filing Information
        "tax_year": int(tax_year) if tax_year and tax_year.isdigit() else None,
        "filing_date": filing_date,
        "filing_status": filing_status,
        
        # Financial Health
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_assets": net_assets,
        "program_ratio": program_ratio,
        "admin_ratio": admin_ratio,
        "fundraising_ratio": fundraising_ratio,
        
        # Governance
        "board_size": voting_members,
        "independent_members": independent_members,
        "governance_rating": governance_rating,
        "has_conflict_policy": conflict_policy,
        "has_whistleblower_policy": whistleblower_policy,
        "has_retention_policy": document_retention_policy,
        
        # Transparency
        "website_url": website,
        "has_website": bool(website)
    }

def get_functional_expenses(root, ns):
    """Existing function - unchanged"""
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