# Phase 1 Verification Report: Ingestion, Metadata & Table Extraction

## 1. Test Suite Results
- **Status**: 9 / 9 Unit Tests Passed (100%)
- **Module**: `ingestion/` (`cleaner.py`, `html_parser.py`, `pdf_parser.py`, `metadata_classifier.py`, `chunker.py`)

---

## 2. Bid Breakdown & Metadata Inference

### Bid1
- **Total Files**: 4
- **Total Chunks**: 189

| File Name | doc_type | Conf | Addendum # | Date | Pages | Chunks |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html` | `bid_page` | 0.98 | - | 05/29/2024 | 1 | 4 |
| `Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf` | `addendum` | 0.95 | 1 | - | 5 | 7 |
| `Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf` | `addendum` | 1.0 | 2 | - | 1 | 1 |
| `JA-207652 Student and Staff Computing Devices FINAL.pdf` | `rfp` | 0.65 | - | - | 62 | 177 |

#### Bid1 Representative Chunk Samples:
**Sample Structured Table Chunk** (`Bid1_JA-207652_Student_and_St_p2_tbl_0` from `JA-207652 Student and Staff Computing Devices FINAL.pdf` p.2):
```markdown
| LENGTH OF CONTRACT | Col_2 |
| --- | --- |
| The term of this proposal shall be for a three (3) year agreement with two (2) successive one (1) year extensions based on the long-range needs of the District and mutual consent of both parties not to exceed five (5) years total. |  |
| SCOPE AND SPECIFICATIONS OF THE PROPOSAL |  |
| The Dallas Independent School District (Dallas ISD or District) is soliciting offers for the goods and/or services specified in this document. 1. Questions concerning this solicitation document should be addressed in writing to the Buyer's Email. 2. Questions must be submitted by the deadline to allow sufficient time for responses prior to receipt/opening date/time. 3. Responses to questions other than administrative questions will be provided to all potential offerors by means of an addendum to the solicitation. All vendors are encouraged to participate even if vendors are the sole source providers. This proposal is being issued in accordance with Title 2 of the Code of Federal Regulations (2CFR) Part 200 |  |
```

**Sample Addendum Chunk** (`Bid1_Addendum_1_RFP_JA-207652_p1_p0` from `Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf` p.1):
```text
The Purpose of this Addendum is to provide responses to the vendors’ questions related to this RFP.
```

**Sample Portal Metadata Chunk** (`Bid1_Student_and_Staff_Comput_p1_p0` from `Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html` p.1):
```text
### Bid Portal Metadata & Information
- **Reference Number**: 00004079100
- **Issuing Organization**: Dallas Independent School District
- **Solicitation Type**: RFP - Request for Proposal (Informal)
- **Solicitation Number**: JA-207652
- **Title**: Student and Staff Computing Devices **SOURCING #168884**
- **Source ID**: SCRIBE
- **Location**: Tex
```

### Bid2
- **Total Files**: 5
- **Total Chunks**: 26

| File Name | doc_type | Conf | Addendum # | Date | Pages | Chunks |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html` | `bid_page` | 0.98 | - | 05/28/2024 | 1 | 3 |
| `Contract_Affidavit.pdf` | `affidavit` | 1.0 | - | - | 3 | 6 |
| `Dell_Laptop_Specs.pdf` | `specs` | 0.67 | - | - | 3 | 3 |
| `Mercury_Affidavit.pdf` | `affidavit` | 1.0 | - | - | 1 | 1 |
| `PORFP_-_Dell_Laptop_Final.pdf` | `rfp` | 1.0 | - | 05/24/2024 | 4 | 13 |

#### Bid2 Representative Chunk Samples:
**Sample Structured Table Chunk** (`Bid2_Contract_Affidavit_pdf_p1_tbl_0` from `Contract_Affidavit.pdf` p.1):
```markdown
| I hereby affirm that I, | Col_2 | Col_3 |
| --- | --- | --- |
|  |  | (title) and duly aut (name of business |
```

**Sample Portal Metadata Chunk** (`Bid2_Dell_Laptops_w_Extended_p1_p0` from `Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html` p.1):
```text
### Bid Portal Metadata & Information
- **Reference Number**: 00004079359
- **Issuing Organization**: State of Maryland Treasurer's Office
- **Solicitation Type**: RFP - Request for Proposal (Informal)
- **Solicitation Number**: BPM044557
- **Title**: Dell Laptops w/Extended Warranty
- **Source ID**: SCRIBE
- **Location**: Anne Arundel County
- **P
```
