import fitz, os, shutil

doc = fitz.open("WEBSCRAPPER/Clinderma_Chatbot_FAQ_Analysis_Report.pdf")
print(f"Total pages: {len(doc)}")
fsize = os.path.getsize("WEBSCRAPPER/Clinderma_Chatbot_FAQ_Analysis_Report.pdf")
print(f"File size: {fsize / 1024:.0f} KB")

os.makedirs("WEBSCRAPPER/pdf_preview", exist_ok=True)
for i, page in enumerate(doc, 1):
    pix = page.get_pixmap(dpi=180)
    pix.save(f"WEBSCRAPPER/pdf_preview/page_{i}.png")
    print(f"  Page {i} rendered")

shutil.copy("WEBSCRAPPER/Clinderma_Chatbot_FAQ_Analysis_Report.pdf",
            "Dataset/Clinderma_Chatbot_FAQ_Analysis_Report.pdf")
shutil.copy("WEBSCRAPPER/Clinderma_Chatbot_FAQ_Analysis_Report.pdf",
            "reports/Clinderma_Chatbot_FAQ_Analysis_Report.pdf")
print("Copied to Dataset/ and reports/")
