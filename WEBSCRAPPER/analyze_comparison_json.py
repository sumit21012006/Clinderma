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
    "WEBSCRAPPER/comparison_results/FAQ_Comparision_General.json",
    "WEBSCRAPPER/comparison_results/FAQ_Comparision_Men.json",
    "WEBSCRAPPER/comparison_results/FAQ_Comparision_Women.json",
    "WEBSCRAPPER/comparison_results/FAQ_Comparision_Teens.json",
    "WEBSCRAPPER/comparison_results/FAQ_Comparision_Acne_Timeline_Expectations.json"
]

all_faqs = []
cohort_summaries = {}

for fpath in files:
    if not os.path.exists(fpath):
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    cohort_name = data.get("cohort", os.path.basename(fpath).replace("FAQ_Comparision_", "").replace(".json", ""))
    results = data.get("results", [])
    summary = data.get("summary", {})
    cohort_summaries[cohort_name] = {
        "summary": summary,
        "results_count": len(results)
    }
    
    for r in results:
        r["cohort_source"] = cohort_name
        all_faqs.append(r)

print(f"Total evaluated FAQs across all cohorts: {len(all_faqs)}")
print(f"Cohort summaries:")
for c, info in cohort_summaries.items():
    print(f"  - {c}: {info['results_count']} FAQs | Summary: {info['summary']}")

# Let's compute global stats
scores = [f["evaluation"]["overall_score"] for f in all_faqs if "evaluation" in f and "overall_score" in f["evaluation"]]
keyword_scores = [f["evaluation"]["keyword_coverage_score"] for f in all_faqs if "evaluation" in f]
keypoint_scores = [f["evaluation"]["keypoint_coverage_score"] for f in all_faqs if "evaluation" in f]

avg_overall = sum(scores) / len(scores) if scores else 0
avg_keywords = sum(keyword_scores) / len(keyword_scores) if keyword_scores else 0
avg_keypoints = sum(keypoint_scores) / len(keypoint_scores) if keypoint_scores else 0

print(f"\nGlobal Average Alignment Score: {avg_overall:.1f}%")
print(f"Global Average Keyword Coverage: {avg_keywords:.1f}%")
print(f"Global Average Keypoint Coverage: {avg_keypoints:.1f}%")

high_align = [f for f in all_faqs if f.get("evaluation", {}).get("overall_score", 0) >= 70]
med_align = [f for f in all_faqs if 40 <= f.get("evaluation", {}).get("overall_score", 0) < 70]
low_align = [f for f in all_faqs if f.get("evaluation", {}).get("overall_score", 0) < 40]

print(f"\nAlignment Distribution:")
print(f"  - High Alignment (>=70%): {len(high_align)} ({len(high_align)/len(all_faqs)*100:.1f}%)")
print(f"  - Moderate Alignment (40-69%): {len(med_align)} ({len(med_align)/len(all_faqs)*100:.1f}%)")
print(f"  - Low Alignment (<40%): {len(low_align)} ({len(low_align)/len(all_faqs)*100:.1f}%)")

# Let's check low alignment questions
print("\nTop 5 Lowest Scoring Questions:")
sorted_faqs = sorted(all_faqs, key=lambda x: x.get("evaluation", {}).get("overall_score", 0))
for i, f in enumerate(sorted_faqs[:5], 1):
    print(f"  {i}. [{f.get('cohort_source')}] {f.get('question')} -> {f.get('evaluation', {}).get('overall_score')}%")

print("\nTop 5 Highest Scoring Questions:")
for i, f in enumerate(sorted(all_faqs, key=lambda x: x.get("evaluation", {}).get("overall_score", 0), reverse=True)[:5], 1):
    print(f"  {i}. [{f.get('cohort_source')}] {f.get('question')} -> {f.get('evaluation', {}).get('overall_score')}%")
