from search.hybrid_retriever import HybridRetriever
from search.eval import EvalBenchmarkItem

r = HybridRetriever()
chunks = r.bm25_index.chunks

test_items = [
    # 1. Exact Match / Identifiers
    EvalBenchmarkItem(
        query_id="Q01_solicitation_id",
        query="What is the official solicitation identifier for the Student and Staff Computing Devices RFP?",
        target_substring="JA-207652",
        expected_file="Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html",
        expected_page=1,
        query_type="exact_match"
    ),
    EvalBenchmarkItem(
        query_id="Q02_emma_project_num",
        query="What is the eMaryland Marketplace Advantage project number for the Dell laptop solicitation?",
        target_substring="BPM044557",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=1,
        query_type="exact_match"
    ),
    EvalBenchmarkItem(
        query_id="Q03_chassis_base_sku",
        query="What is the manufacturer base SKU code for the Dell Latitude 5550 XCTO laptop?",
        target_substring="210-BLYZ",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="specs"
    ),
    EvalBenchmarkItem(
        query_id="Q04_processor_sku",
        query="What part number is assigned to the Intel Core Ultra 5 125U processor in the laptop specs?",
        target_substring="379-BFNZ",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="specs"
    ),
    EvalBenchmarkItem(
        query_id="Q05_agency_contact_email",
        query="What is the designated email address for the Maryland State Treasurer procurement contact?",
        target_substring="thawkins@treasurer.state.md.us",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="exact_match"
    ),
    EvalBenchmarkItem(
        query_id="Q06_agency_contact_phone",
        query="What telephone number should be used to contact the procurement officer in the Maryland laptop RFP?",
        target_substring="410-260-7533",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="exact_match"
    ),

    # 2. Specifications & Quantities
    EvalBenchmarkItem(
        query_id="Q07_addendum_usb_spec",
        query="What type of USB port revision is mandated for the non-touch display in Addendum 1?",
        target_substring="3.1 USB port",
        expected_file="Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf",
        expected_page=1,
        query_type="specs"
    ),
    EvalBenchmarkItem(
        query_id="Q08_laptop_order_quantity",
        query="What business need and hardware refresh reason is documented under Scope of Work?",
        target_substring="refresh of laptops",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="specs"
    ),
    EvalBenchmarkItem(
        query_id="Q09_power_adapter_rating",
        query="What wattage power adapter must be supplied with the Dell notebooks?",
        target_substring="65W AC adapter",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="specs"
    ),
    EvalBenchmarkItem(
        query_id="Q10_memory_config",
        query="What system RAM memory capacity and module layout is required for the laptops?",
        target_substring="16 GB: 2 x 8 GB, DDR5",
        expected_file="Dell_Laptop_Specs.pdf",
        expected_page=1,
        query_type="specs"
    ),

    # 3. Dates & Logistics
    EvalBenchmarkItem(
        query_id="Q11_addendum2_deadline_extension",
        query="What is the revised proposal submission deadline after Addendum 2 was issued for Dallas ISD?",
        target_substring="July 9, 2024 at 2:00 PM CST",
        expected_file="Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf",
        expected_page=1,
        query_type="dates"
    ),
    EvalBenchmarkItem(
        query_id="Q12_delivery_destination",
        query="What physical street address is specified for equipment delivery to the Treasurer's office?",
        target_substring="80 Calvert Street",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="dates"
    ),
    EvalBenchmarkItem(
        query_id="Q13_initial_contract_term",
        query="Who is the assigned purchasing buyer and email for the Dallas ISD devices solicitation?",
        target_substring="JALZATE@dallasisd.org",
        expected_file="JA-207652 Student and Staff Computing Devices FINAL.pdf",
        expected_page=2,
        query_type="dates"
    ),
    EvalBenchmarkItem(
        query_id="Q14_questions_deadline_portal",
        query="What is the internal sourcing portal reference number for the Dallas ISD procurement?",
        target_substring="00004079100",
        expected_file="Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html",
        expected_page=1,
        query_type="dates"
    ),

    # 4. Legal, Compliance & Affidavits
    EvalBenchmarkItem(
        query_id="Q15_mercury_free_affirmation",
        query="What environmental statement must vendors verify in the Mercury Affidavit?",
        target_substring="product(s) offered do not contain mercury",
        expected_file="Mercury_Affidavit.pdf",
        expected_page=1,
        query_type="legal"
    ),
    EvalBenchmarkItem(
        query_id="Q16_contract_affidavit_authority",
        query="What authority affirmation must the representative state in the Contract Affidavit?",
        target_substring="duly authorized representative",
        expected_file="Contract_Affidavit.pdf",
        expected_page=1,
        query_type="legal"
    ),
    EvalBenchmarkItem(
        query_id="Q17_award_evaluation_basis",
        query="What is the basis for award recommendation in the Maryland laptop procurement?",
        target_substring="most advantageous to the State",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=4,
        query_type="legal"
    ),
    EvalBenchmarkItem(
        query_id="Q18_addendum1_clarifications",
        query="How does Addendum 1 address the submission of additional warranty options and pricing?",
        target_substring="system will only take one input",
        expected_file="Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf",
        expected_page=1,
        query_type="legal"
    ),

    # 5. Paraphrased Queries
    EvalBenchmarkItem(
        query_id="Q19_para_due_date_bid1",
        query="When do vendor bids have to be turned in for the school computing devices contract?",
        target_substring="July 9, 2024 at 2:00 PM CST",
        expected_file="Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf",
        expected_page=1,
        query_type="paraphrased"
    ),
    EvalBenchmarkItem(
        query_id="Q20_para_prebid_meeting",
        query="Is there a vendor pre-proposal conference scheduled for the Dallas school district bid?",
        target_substring="Pre-Proposal Meeting",
        expected_file="JA-207652 Student and Staff Computing Devices FINAL.pdf",
        expected_page=2,
        query_type="paraphrased"
    ),
    EvalBenchmarkItem(
        query_id="Q21_para_warranty_support",
        query="What extended manufacturer warranty duration is required for the Maryland machines?",
        target_substring="3 years following the date of delivery",
        expected_file="PORFP_-_Dell_Laptop_Final.pdf",
        expected_page=3,
        query_type="paraphrased"
    ),
    EvalBenchmarkItem(
        query_id="Q22_para_mwbe_inquiry",
        query="What inquiry was submitted regarding the Dallas ISD purchasing and M/WBE team reaching out to references?",
        target_substring="purchasing/M/WBE team will be reaching out",
        expected_file="Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf",
        expected_page=2,
        query_type="paraphrased"
    ),
]

all_ok = True
for it in test_items:
    matched = False
    for c in chunks:
        if it.target_substring.lower() in c.text.lower():
            if it.expected_file.lower() in c.metadata.file_name.lower():
                p_start = c.metadata.page_start or c.metadata.page_number
                p_end = c.metadata.page_end or c.metadata.page_number
                if p_start <= it.expected_page <= p_end:
                    matched = True
                    break
    if not matched:
        print(f"FAILED: {it.query_id} (target: '{it.target_substring}' in {it.expected_file} p.{it.expected_page})")
        all_ok = False
    else:
        print(f"PASSED: {it.query_id}")

print("ALL ITEMS VERIFIED:", all_ok)
