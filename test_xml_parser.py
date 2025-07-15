#!/usr/bin/env python3

from xml_parser import extract_990_data
import json

def test_xml_parser():
    # Test with the ProPublica XML URL you shared earlier
    test_xml_url = "https://pp-990-xml.s3.us-east-1.amazonaws.com/202432749349301153_public.xml?response-content-disposition=inline&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIA266MJEJYTM5WAG5Y%2F20250715%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250715T205806Z&X-Amz-Expires=1800&X-Amz-SignedHeaders=host&X-Amz-Signature=a0f0f01632b85d75edbbdcd673151d4b47986175eafd9b7428cb6e629d827b6d"
    
    print("🧪 Testing XML parser with transparency metrics...")
    print(f"📄 URL: {test_xml_url[:100]}...")
    
    try:
        result = extract_990_data(test_xml_url)
        
        print("\n✅ SUCCESS! Here's what we extracted:")
        print("\n📊 FUNCTIONAL EXPENSES:")
        print(json.dumps(result["functional_expenses"], indent=2))
        
        print("\n🌟 TRANSPARENCY METRICS:")
        print(json.dumps(result["transparency_metrics"], indent=2))
        
        print("\n📝 MISSION INFO:")
        print(f"Mission fields found: {len(result['mission_fields'])}")
        if result['mission_fields']:
            print(f"First mission: {result['mission_fields'][0][:100]}...")
        
        print("\n🎯 PROGRAMS:")
        print(f"Programs found: {len(result['short_programs'])}")
        for i, prog in enumerate(result['short_programs'][:3]):  # Show first 3
            print(f"  {i+1}. {prog['short'][:50]}...")
        
        return result
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = test_xml_parser()
    
    if result:
        print("\n🎉 Test completed successfully!")
        print("\n💡 Key metrics extracted:")
        tm = result["transparency_metrics"]
        print(f"   Tax Year: {tm.get('tax_year')}")
        print(f"   Program Ratio: {tm.get('program_ratio')}%")
        print(f"   Board Size: {tm.get('board_size')}")
        print(f"   Governance: {tm.get('governance_rating')}")
        print(f"   Website: {tm.get('website_url')}")
    else:
        print("\n💥 Test failed - check errors above")