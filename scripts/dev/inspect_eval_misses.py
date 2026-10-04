import json
from search.eval import BENCHMARK_ITEMS
from search.bm25_index import BM25Index

items_dict = {item.query_id: item for item in BENCHMARK_ITEMS}
data = json.load(open("outputs/search_eval_results.json"))

idx = BM25Index.load()

print("--- Checking Missing Benchmark Items ---")
for qid in ["Q07_addendum1_usb", "Q13_mercury_affidavit", "Q14_contract_affidavit", "Q16_prebid_conference", "Q17_questions_due", "Q18_warranty_fa"]:
    item = items_dict[qid]
    print(f"\nItem: {qid}")
    print(f"Target substring: '{item.target_substring}'")
    print(f"Expected file: '{item.expected_file}', page: {item.expected_page}")

    # Check if target substring actually exists in any chunk of the expected file
    found_in_chunks = []
    for meta in idx.chunk_metadata:
        if item.expected_file.lower() in meta["file_name"].lower():
            if item.target_substring.lower() in meta["text"].lower():
                found_in_chunks.append((meta["chunk_id"], meta["page_number"]))

    print(f"Found in index chunks of expected file: {found_in_chunks}")

    # Print the top 3 results for this query in Hybrid+Rerank
    rerank_results = [r for r in data["details"]["hybrid"] if r["query_id"] == qid][0]
    print(f"Rerank matched rank: {rerank_results['matched_rank']}")
    print(f"Top citation: {rerank_results['top_result_citation']}")
