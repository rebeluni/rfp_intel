# Phase 1 Verification Report: Ingestion, Metadata & Table Extraction

## 1. Test Suite Results
- **Status**: 9 / 9 Unit Tests Passed (100%)
- **Module**: `ingestion/` (`cleaner.py`, `html_parser.py`, `pdf_parser.py`, `metadata_classifier.py`, `chunker.py`)

---

## 2. Bid Breakdown & Metadata Inference

### Bid1
- **Total Files**: 4
- **Total Chunks**: 211

| File Name | doc_type | Conf | Addendum # | Date | Pages | Chunks |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html` | `bid_page` | 0.98 | - | 05/29/2024 11:16 AM EDT | 1 | 2 |
| `Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf` | `addendum` | 0.95 | 1 | - | 5 | 7 |
| `Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf` | `addendum` | 1.0 | 2 | - | 1 | 1 |
| `JA-207652 Student and Staff Computing Devices FINAL.pdf` | `rfp` | 0.6 | - | - | 62 | 201 |

#### Bid1 Representative Chunk Samples:
**Sample Structured Table Chunk** (`Bid1_JA_207652_Student_and_Staff_Computing_Devices_FINAL_p33_tbl_0_c7911802` from `JA-207652 Student and Staff Computing Devices FINAL.pdf` p.33):
```markdown
[Bid1 | RFP | JA-207652 Student and Staff Comp... | p.33 | Section: Specification Table]
| Name | Data Type | Description |
| --- | --- | --- |
| MWBE Forms | File | MWBE Forms must be completed and attached regardless if you are MWBE status |
| W9 Form | File | W9 Form completed, signed and attached to the submission |
| Punch Out Process - OPTIONAL | File | Punch Out Process - OPTIONAL |
```

**Sample Addendum Chunk** (`Bid1_Addendum_1_RFP_JA_207652_Student_and_Staff_Computing_Devices_p1_c0_ed033b44` from `Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf` p.1):
```text
[Bid1 | Addendum 1 | Addendum 1 RFP JA-207652 Student... | p.1 | Section: General]
The Purpose of this Addendum is to provide responses to the vendors’ questions related to this RFP.
```

**Sample Portal Metadata Chunk** (`Bid1_Student_and_Staff_Computing_Devices_SOURCING_168884_Bid_Information_3_BidNet_Direct_p1_c0_db37acf2` from `Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html` p.1):
```text
[Bid1 | Portal Summary | Student and Staff Computing Devi... | p.1 | Section: Scope & Description]
### Portal Bid Details & Schedule
- **Reference Number**: 00004079100
- **Issuing Organization**: Dallas Independent School District
- **Solicitation Type**: RFP - Request for Proposal (Informal)
- **Solicitation Number**: JA-207652
- **Title**: Stude
```

### Bid2
- **Total Files**: 5
- **Total Chunks**: 24

| File Name | doc_type | Conf | Addendum # | Date | Pages | Chunks |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html` | `bid_page` | 0.98 | - | 05/28/2024 11:47 AM EDT | 1 | 1 |
| `Contract_Affidavit.pdf` | `affidavit` | 0.93 | - | - | 3 | 5 |
| `Dell_Laptop_Specs.pdf` | `specs` | 0.67 | - | - | 3 | 3 |
| `Mercury_Affidavit.pdf` | `affidavit` | 1.0 | - | - | 1 | 1 |
| `PORFP_-_Dell_Laptop_Final.pdf` | `rfp` | 1.0 | - | 05/24/2024 | 4 | 14 |

#### Bid2 Representative Chunk Samples:
**Sample Structured Table Chunk** (`Bid2_PORFP_Dell_Laptop_Final_p3_tbl_0_part0_a7803070` from `PORFP_-_Dell_Laptop_Final.pdf` p.3):
```markdown
[Bid2 | RFP | PORFP_-_Dell_Laptop_Final | p.3 | Section: Specification Table]
| Agency POC Name: | Field 2 | Field 3 | Field 4 | Tamaira Hawkins | Field 6 | Field 7 | Field 8 | Field 9 | Agency POC | Field 11 | Field 12 | Field 13 | Field 14 | Field 15 | 410-260-7533 | Field 17 | Field 18 | Field 19 | Field 20 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  | Phone Number: |  |  |  |  |  |  |  |  |  |  |
| Agency POC Email Address: |  |  |  | thawkins@treasurer.state.md .us |  |  |  | Agency POC Fax: | Agency POC |  |  |  |  |  | N/A |  |  |  |  |
|  |  |  |  |  |  |  |  |  | Fax: |  |  |  |  |  |  |  |  |  |  |
| Agency POC Mailing Address: |  |  |  | MD State Treasurer’s Office 80 Calvert Street, Room 109 Annapolis, MD 21401 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  | Section 3 – Delivery Address / Work Site POC Information (if different from above) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
|  | Agency On-site Contact |  |  | James Simpson |  |  |  |  | Agency On-site |  |  |  |  |  | 410-260-6063 |  |  |  |  |
|  | Name: |  |  |  |  |  |  |  | Phone Number: |  |  |  |  |  |  |  |  |  |  |
```

**Sample Portal Metadata Chunk** (`Bid2_Dell_Laptops_w_Extended_Warranty_Bid_Information_3_BidNet_Direct_p1_c0_59cb8c34` from `Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html` p.1):
```text
[Bid2 | Portal Summary | Dell Laptops w_Extended Warranty... | p.1 | Section: Scope & Description]
### Portal Bid Details & Schedule
- **Reference Number**: 00004079359
- **Issuing Organization**: State of Maryland Treasurer's Office
- **Solicitation Type**: RFP - Request for Proposal (Informal)
- **Solicitation Number**: BPM044557
- **Title**: Del
```
