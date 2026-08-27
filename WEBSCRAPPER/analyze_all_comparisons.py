import json
import glob
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

files = [
    ("General", "WEBSCRAPPER/comparison_results/FAQ_Comparision_General.json"),
    ("Men", "WEBSCRAPPER/comparison_results/FAQ_Comparision_Men.json"),
    ("Women", "WEBSCRAPPER/comparison_results/FAQ_Comparision_Women.json"),
    ("Teens", "WEBSCRAPPER/comparison_results/FAQ_Comparision_Teens.json"),
    ("Acne Timeline & Expectations", "WEBSCRAPPER/comparison_results/FAQ_Comparision_Acne_Timeline_Expectations.json")
]

all_results = []
cohort_stats = {}
category_stats = {}

for cohort_name, fpath in files:
    if not os.path.exists(fpath):
        print(f"Warning: {fpath} does not exist")
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    meta = data.get("metadata", {})
    results = data.get("results", [])
    
    c_scores = [r.get("alignment_score", 0) for r in results]
    c_kw = [r.get("keyword_coverage", {}).get("coverage_percent", 0) for r in results]
    c_kp = [r.get("key_point_coverage", {}).get("score_percent", 0) for r in results]
    c_time = [r.get("duration_seconds", 0) for r in results if r.get("duration_seconds")]

    cohort_stats[cohort_name] = {
        "count": len(results),
        "avg_alignment": sum(c_scores) / len(c_scores) if c_scores else 0,
        "avg_keyword": sum(c_kw) / len(c_kw) if c_kw else 0,
        "avg_keypoint": sum(c_kp) / len(c_kp) if c_kp else 0,
        "avg_time": sum(c_time) / len(c_time) if c_time else 0,
        "timestamp": meta.get("timestamp", "N/A")
    }

    for r in results:
        r["cohort_name"] = cohort_name
        all_results.append(r)
        
        cat = r.get("category", "Uncategorized")
        if cat not in category_stats:
            category_stats[cat] = []
        category_stats[cat].append(r)

print(f"=== GLOBAL STATS (Total FAQs: {len(all_results)}) ===")
all_scores = [r.get("alignment_score", 0) for r in all_results]
all_kw = [r.get("keyword_coverage", {}).get("coverage_percent", 0) for r in all_results]
all_kp = [r.get("key_point_coverage", {}).get("score_percent", 0) for r in all_results]
all_times = [r.get("duration_seconds", 0) for r in all_results if r.get("duration_seconds")]

print(f"Overall Average Alignment Score: {sum(all_scores)/len(all_scores):.2f}%")
print(f"Overall Average Keyword Coverage: {sum(all_kw)/len(all_kw):.2f}%")
print(f"Overall Average Key Point Coverage: {sum(all_kp)/len(all_kp):.2f}%")
print(f"Average Response Latency: {sum(all_times)/len(all_times):.2f}s")

print("\n=== COHORT BREAKDOWN ===")
for c, s in cohort_stats.items():
    print(f"{c:30s}: {s['count']:2d} FAQs | Alignment: {s['avg_alignment']:5.1f}% | Keywords: {s['avg_keyword']:5.1f}% | KeyPoints: {s['avg_keypoint']:5.1f}% | Latency: {s['avg_time']:.1f}s")

print("\n=== CATEGORY BREAKDOWN ===")
for cat, items in sorted(category_stats.items()):
    scores = [i.get("alignment_score", 0) for i in items]
    print(f"{cat:35s}: {len(items):2d} FAQs | Avg Score: {sum(scores)/len(scores):5.1f}%")

high_align = [r for r in all_results if r.get("alignment_score", 0) >= 70]
med_align = [r for r in all_results if 50 <= r.get("alignment_score", 0) < 70]
low_align = [r for r in all_results if r.get("alignment_score", 0) < 50]

print(f"\nAlignment Distribution:")
print(f"  - High Alignment (>=70%):     {len(high_align):2d} ({len(high_align)/len(all_results)*100:.1f}%)")
print(f"  - Moderate Alignment (50-69%): {len(med_align):2d} ({len(med_align)/len(all_results)*100:.1f}%)")
print(f"  - Low Alignment (<50%):        {len(low_align):2d} ({len(low_align)/len(all_results)*100:.1f}%)")

print("\n=== TOP 5 LOWEST SCORING FAQS (Gaps to address) ===")
for i, r in enumerate(sorted(all_results, key=lambda x: x.get("alignment_score", 0))[:5], 1):
    print(f"{i}. [{r['cohort_name']}] {r['question']}")
    print(f"   Score: {r['alignment_score']:.1f}% | Missing KP: {r.get('key_point_coverage', {}).get('uncovered_key_points', [])[:1]}")

print("\n=== TOP 5 HIGHEST SCORING FAQS ===")
for i, r in enumerate(sorted(all_results, key=lambda x: x.get("alignment_score", 0), reverse=True)[:5], 1):
    print(f"{i}. [{r['cohort_name']}] {r['question']} -> {r['alignment_score']:.1f}%")
