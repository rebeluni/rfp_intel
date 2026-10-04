import json

data = json.load(open("outputs/search_eval_results.json", encoding="utf-8"))

for mode in ["dense_only", "bm25_only", "hybrid_norerank", "hybrid"]:
    print(f"\n=================== MODE: {mode} ===================")
    for item in data["details"][mode]:
        if item["matched_rank"] is None or item["matched_rank"] > 3:
            print(f"[{item['query_id']}] Rank: {item['matched_rank']}")
            print(f"   Query: {item['query']}")
            print(f"   Top Citation: {item['top_result_citation']}")
            print(f"   Top Snippet: {item['top_result_snippet'][:140]}...")
