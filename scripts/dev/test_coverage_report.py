import sys, os
sys.path.insert(0, os.path.abspath("."))
from ingestion.pdf_parser import PDFParser
doc = PDFParser.parse('Bid1/JA-207652 Student and Staff Computing Devices FINAL.pdf', 'Bid1')
cov = doc.coverage_report
print('Coverage file:', cov['file_name'])
print('Total pages:', cov['total_pages'])
print('Has vector outlines:', cov['has_vector_outlines'])
print('Non-extractable pages:', cov['non_extractable_pages'])
print('Form widget pages:', cov['form_widget_pages'])
for p in cov['pages']:
    pno = p['page_number']
    if pno in [54, 55, 56, 57, 58, 59]:
        print(f"Page {pno}: status={p['status']}, widgets={p['widget_count']}, text_len={p['char_count']}")
