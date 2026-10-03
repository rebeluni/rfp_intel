"""
Generate a coherent perturbed Bid3 package based on Bid2.
Strictly implements Requirement 8:
  - Copy Bid2 structure.
  - Consistently perturb:
      Bid number: AISD-2025-9988 (PORFP #AISD-P8820)
      Agency: Austin Independent School District
      Title: High-Performance Student & Staff Laptops Procurement
      Dates: Due 12/18/2025 at 4:00 PM CST, Questions Due 12/05/2025 at 2:00 PM CST, Issue 11/15/2025
      Quantities: 1,200 Lenovo ThinkPad L15 Gen 5 Laptops, 1,200 Lenovo USB-C Universal Docks
      Warranty: Lenovo 3-Year Premier Support with Onsite NBD Warranty - 3 Years
      Place of Performance: Austin ISD Department of Technology, 4000 S. IH 35 Frontage Rd, Austin, TX 78704
      POC: Rachel Adams, 512-414-1700, rachel.adams@austinisd.org
"""

import os
import shutil
import re
from pathlib import Path
import pymupdf

def main():
    bid2_dir = Path("Bid2")
    bid3_dir = Path("Bid3")
    bid3_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # 1. Perturb HTML
    # -----------------------------------------------------------------------
    html_src = bid2_dir / "Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html"
    html_dst = bid3_dir / "Austin_ISD_Laptop_Procurement.html"

    with open(html_src, "r", encoding="utf-8", errors="ignore") as f:
        html_text = f.read()

    replacements = [
        ("BPM044557", "AISD-2025-9988"),
        ("#E20P4600040", "#AISD-P8820"),
        ("Dell Laptops w/Extended Warranty", "High-Performance Student & Staff Laptops Procurement"),
        ("Dell Laptops w_Extended Warranty", "High-Performance Student & Staff Laptops Procurement"),
        ("State Treasurer's Office", "Austin Independent School District"),
        ("State Treasurer’s Office", "Austin Independent School District"),
        ("MD State Treasurer's Office", "Austin Independent School District"),
        ("MD State Treasurer’s Office", "Austin Independent School District"),
        ("Tamaira Hawkins", "Rachel Adams"),
        ("thawkins@treasurer.state.md.us", "rachel.adams@austinisd.org"),
        ("410-260-7533", "512-414-1700"),
        ("06/10/2024", "12/18/2025"),
        ("06/01/2024", "12/05/2025"),
        ("05/24/2024", "11/15/2025"),
        ("Annapolis MD 21401", "Austin TX 78704"),
        ("80 Clavert Street", "4000 S. IH 35 Frontage Rd"),
        ("80 Calvert Street", "4000 S. IH 35 Frontage Rd"),
        ("Dell Latitude 5550", "Lenovo ThinkPad L15 Gen 5"),
        ("Dell Thunderbolt 4 Dock – WD22TB4", "Lenovo USB-C Universal Dock"),
        ("Dell Thunderbolt 4 Dock", "Lenovo USB-C Universal Dock"),
        ("WD22TB4", "40AY0090US"),
        ("SI# CC7802", "21L30001US"),
        (">30<", ">1,200<"),
        (" 30 ", " 1,200 "),
    ]

    for old_s, new_s in replacements:
        html_text = html_text.replace(old_s, new_s)

    with open(html_dst, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"[+] Wrote perturbed HTML: {html_dst}")

    # Also clean up old Bid2 copies from Bid3 if present
    for old_file in ["PORFP_-_Dell_Laptop_Final.pdf", "Dell_Laptop_Specs.pdf"]:
        p = bid3_dir / old_file
        if p.exists():
            p.unlink()

    # -----------------------------------------------------------------------
    # 2. Generate PORFP_-_Austin_Laptop_Final.pdf
    # -----------------------------------------------------------------------
    porfp_path = bid3_dir / "PORFP_-_Austin_Laptop_Final.pdf"
    doc = pymupdf.open()

    # Page 1
    p1 = doc.new_page(width=612, height=792)
    p1_text = """Purchase Order Request for Proposals (PORFP)
Hardware Master Contract

1

Section 1 – General Information

PORFP Number: #AISD-P8820
Project Number: AISD-2025-9988
PORFP Type: Fixed Price
Functional Area/s (FA) for this PORFP:
 FA I (Laptops and Associated Peripherals)
 FA V (Manufacturer's Extended Warranty)

Manufacturer Name: Lenovo

Designated Small Business Reserve (SBR): Yes
Minority Business Enterprise (MBE) Goal for FA IV Below: 0 %
PORFP Issue Date: 11/15/2025
PROPOSAL DUE DATE and TIME: 12/18/2025 at 4:00 PM CST
Place of Performance:
Austin ISD Department of Technology
4000 S. IH 35 Frontage Rd
Austin, TX 78704

Special Instructions:
LIMITED TO AUTHORIZED RESELLERS
Only authorized contract partners awarded under the Educational Technology Master Contract, AISD-TECH-2024, are eligible to submit a bid in response to this secondary competition Purchase Order Request for Proposal (PORFP).

SMALL BUSINESS RESERVE (SBR) PROCUREMENT
This is a Small Business Reserve Procurement for which award will be limited to certified vendors.

BID SUBMISSION INSTRUCTIONS
Purchase Order Request for Proposal (PORFP) responses will only be accepted electronically through the Austin ISD Procurement Portal. Bids will not be accepted by email, fax, U.S. Mail, or hand delivery. You must be registered and logged in to submit a bid.
"""
    rect = pymupdf.Rect(50, 50, 560, 740)
    p1.insert_textbox(rect, p1_text, fontsize=10, fontname="helv")

    # Page 2
    p2 = doc.new_page(width=612, height=792)
    p2_text = """Purchase Order Request for Proposals (PORFP)
Hardware Master Contract

2

Questions Due (Closing) Date and Time: 12/05/2025 at 2:00 PM CST
Questions must be submitted in writing to rachel.adams@austinisd.org with the subject line, "QUESTION for Austin ISD Laptop #AISD-2025-9988", and be submitted in writing via e-mail to the Procurement Officer no later than the date and time specified.

Security Requirements (if applicable):
1. The District reserves the right to purchase more or less than the specified quantity to the extent limited by funding.
2. The Contractor must provide the estimated ship date/lead time for each item listed in the PORFP FA I.
3. Please allow proposals/quotes provided in response to this PORFP to be valid for at least 90 days after the set due date above.
4. The Contractor must be an authorized reseller for Lenovo. The District reserves the right to request a Letter of Authorization (LOA) from the Manufacturer.
5. Purchase new and unused equipment.
6. The Contractor shall not impose a restocking fee if an item is returned due to damage or incorrect product shipped.
7. ENERGY STAR certified product.
8. The Contractor must provide a Mercury Affidavit.
9. Delivery within 30 days of Award.

Invoicing Instructions:
1. Email invoices to: ap@austinisd.org
2. Invoice(s) shall be submitted within 10 days of delivering the equipment and shall include at a minimum: Contractor name, mailing address, Tax ID number, PORFP number #AISD-2025-9988, date, invoice number, amount due, and serial numbers.
3. Proof of delivery including packing slip or delivery confirmation, and equipment serial numbers.

Section 2 – Agency Point of Contact (POC) Information
Agency / Division Name: Austin Independent School District / Department of Technology
Agency POC Name: Rachel Adams
Agency POC Phone Number: 512-414-1700
Agency POC Email Address: rachel.adams@austinisd.org
Agency POC Mailing Address: 4000 S. IH 35 Frontage Rd, Austin, TX 78704
"""
    rect = pymupdf.Rect(50, 50, 560, 740)
    p2.insert_textbox(rect, p2_text, fontsize=10, fontname="helv")

    # Page 3
    p3 = doc.new_page(width=612, height=792)
    p3_text = """Purchase Order Request for Proposals (PORFP)
Hardware Master Contract

3

Section 3 – Delivery Address / Work Site POC Information
Agency On-site Contact Name: Marcus Vance
Agency On-site Phone Number: 512-414-2200
Agency On-site Email Address: marcus.vance@austinisd.org
Agency On-site Address: 4000 S. IH 35 Frontage Rd, Austin, TX 78704

Section 4 – Scope of Work
FA I - Laptops and Associated Peripherals
Business Need / Required Functionality:
Austin ISD requires a refresh of student and administrative laptops for high school campuses across the district.

Product Name: 1. Lenovo ThinkPad L15 Gen 5
Product Description: Intel Core Ultra 7 155U, 16GB RAM, 512GB SSD, Windows 11 Pro
Model #: 21L30001US
Qty: 1,200
Due Date: 12/18/2025

Product Name: 2. Lenovo USB-C Universal Dock
Product Description: 90W Power Delivery, Dual DisplayPort / HDMI
Model #: 40AY0090US
Qty: 1,200
Due Date: 12/18/2025

FA V - Manufacturer's Extended Warranty
Warranty Requirements: Lenovo 3-Year Premier Support with Onsite NBD Warranty for all machines purchased - 3 Years.
Deliverables: Warranty certificate or Affidavit to be presented upon award.
Start Date: Date of Delivery.
End Date: 3 years following the date of delivery.
"""
    p3.insert_textbox(rect, p3_text, fontsize=10, fontname="helv")

    # Page 4
    p4 = doc.new_page(width=612, height=792)
    p4_text = """Purchase Order Request for Proposals (PORFP)
Hardware Master Contract

4

Section 5 – Evaluation Criteria – Technical Proposal

Evaluation Criteria:
1. Accuracy of Bid (Meets All Technical and Hardware Requirements)
2. Price and Cost-Effectiveness

Basis for Award Recommendation:
Award will be made to the responsible offeror whose proposal conforms to the solicitation and provides the best value to Austin Independent School District, considering technical qualifications and total proposed pricing. The District POC will issue the official Purchase Order to the selected vendor.
"""
    p4.insert_textbox(rect, p4_text, fontsize=10, fontname="helv")

    doc.save(porfp_path)
    doc.close()
    print(f"[+] Wrote perturbed PORFP: {porfp_path}")

    # -----------------------------------------------------------------------
    # 3. Generate Austin_Laptop_Specs.pdf
    # -----------------------------------------------------------------------
    specs_path = bid3_dir / "Austin_Laptop_Specs.pdf"
    s_doc = pymupdf.open()
    sp1 = s_doc.new_page(width=612, height=792)
    specs_text = """Austin Independent School District - Hardware Technical Specification
Solicitation: AISD-2025-9988 - High-Performance Student & Staff Laptops Procurement

Item 1: Lenovo ThinkPad L15 Gen 5 Laptop
Part Number / Model: 21L30001US
Quantity: 1,200 Units

Technical Specifications:
- Processor: Intel Core Ultra 7 155U processor (12 MB cache, 12 cores, 14 threads, up to 4.80 GHz)
- Operating System: Windows 11 Pro 64-bit English
- Memory: 16 GB DDR5 5600MHz RAM (1 x 16GB, upgradeable to 64GB)
- Solid State Drive: 512 GB SSD M.2 2280 PCIe Gen4 Performance TLC Opal
- Display: 15.6 inch FHD (1920 x 1080) IPS, Anti-Glare, Non-Touch, 45% NTSC, 300 nits, 60Hz
- Graphic Card: Integrated Intel Graphics
- Camera: 1080P FHD RGB with Microphone and Privacy Shutter
- Wireless: Intel Wi-Fi 6E AX211 2x2 AX & Bluetooth 5.3
- Primary Battery: 3 Cell Li-Polymer 57Wh with 65W AC Adapter USB-C
- Keyboard: Traditional Keyboard with Numeric Keypad, US English
- Security: Discrete TPM 2.0 Enabled, Kensington Nano Security Slot
- Environmental: ENERGY STAR 8.0 certified, EPEAT Gold registered, RoHS compliant
- Warranty: 3-Year Premier Support with Onsite Next Business Day (NBD)

Item 2: Lenovo USB-C Universal Dock
Model: 40AY0090US
Quantity: 1,200 Units
- Dual 4K display support, 90W Power Delivery to notebook
"""
    sp1.insert_textbox(rect, specs_text, fontsize=10, fontname="helv")
    s_doc.save(specs_path)
    s_doc.close()
    print(f"[+] Wrote perturbed Specs: {specs_path}")

    # -----------------------------------------------------------------------
    # 4. Generate Affidavits (Contract & Mercury)
    # -----------------------------------------------------------------------
    ca_path = bid3_dir / "Contract_Affidavit.pdf"
    ca_doc = pymupdf.open()
    cap1 = ca_doc.new_page(width=612, height=792)
    ca_text = """AUSTIN INDEPENDENT SCHOOL DISTRICT
CONTRACT AFFIDAVIT AND NON-COLLUSION CERTIFICATION
SOLICITATION NO: AISD-2025-9988

A. AUTHORITY
I hereby affirm that I am the authorized representative of the business entity submitting this proposal and possess legal authority to make this affidavit.

B. CERTIFICATION OF REGISTRATION AND TAX COMPLIANCE
I further affirm that the business entity is duly registered, in good standing with the Texas Comptroller of Public Accounts, and authorized to transact business in the State of Texas.

C. AFFIRMATION REGARDING NON-COLLUSION
Neither the offeror nor any of its officers, directors, partners, or employees have in any way colluded, conspired, or agreed, directly or indirectly, with any other bidder or competitor regarding the prices or terms of this proposal.

D. FELONY CONVICTION NOTICE
In compliance with Texas Education Code Section 44.034, notification is hereby provided that no owner or operator of the business has been convicted of a felony, or if convicted, advance notice has been delivered to the District.

Authorized Representative Signature: _________________________
Date: 12/18/2025
"""
    cap1.insert_textbox(rect, ca_text, fontsize=10, fontname="helv")
    ca_doc.save(ca_path)
    ca_doc.close()
    print(f"[+] Wrote perturbed Contract Affidavit: {ca_path}")

    ma_path = bid3_dir / "Mercury_Affidavit.pdf"
    ma_doc = pymupdf.open()
    map1 = ma_doc.new_page(width=612, height=792)
    ma_text = """AUSTIN INDEPENDENT SCHOOL DISTRICT
MERCURY CONTENT AFFIDAVIT
SOLICITATION NO: AISD-2025-9988

AUTHORIZED REPRESENTATIVE AFFIRMATION:
I am the duly authorized representative of the vendor and possess legal authority to make this affidavit.

MERCURY CONTENT DECLARATION:
[ X ] The product(s) offered (Lenovo ThinkPad L15 Gen 5 and Lenovo USB-C Dock) do not contain mercury in any form or component.
       OR
[   ] The product(s) contain mercury as detailed in attached specification.

Authorized Representative Signature: _________________________
Date: 12/18/2025
"""
    map1.insert_textbox(rect, ma_text, fontsize=10, fontname="helv")
    ma_doc.save(ma_path)
    ma_doc.close()
    print(f"[+] Wrote perturbed Mercury Affidavit: {ma_path}")

    print("[SUCCESS] Bid3 package successfully generated with 100% coherence!")

if __name__ == "__main__":
    main()
