"""Generates the FICTIONAL legal-notice and offer-letter sample PDFs used by the tests and the demo (all names, addresses and numbers are invented).
    python -m tests.make_sample_pdfs
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent / "fixtures"
ss = getSampleStyleSheet()


def make(name, blocks):
    OUT.mkdir(exist_ok=True)
    doc = SimpleDocTemplate(str(OUT / name), pagesize=A4, title=name)
    story = [Paragraph("SAMPLE DOCUMENT — FICTIONAL, FOR TESTING ONLY", ss["Italic"]), Spacer(1, 8)]
    for b in blocks:
        story.append(PageBreak() if b == "PAGEBREAK" else Paragraph(b, ss["Heading2"] if b.isupper() else ss["BodyText"]))
        story.append(Spacer(1, 6))
    doc.build(story)


make("sample_legal_notice_received.pdf", [
    "LEGAL NOTICE",
    "Date: 20 October 2026. By Registered Post A.D.",
    "To: Mr. Vikram Singh, House No. 45, Sector 12, Noida, Uttar Pradesh.",
    "Under instructions from my client M/s QuickFurnish Rentals Pvt. Ltd., I hereby serve you this notice.",
    "1. You rented furniture from my client under Agreement No. QF/2025/8812 dated 10 January 2025 at a monthly rent of Rs 2,400.",
    "2. You have failed to pay rent for July, August and September 2026, amounting to Rs 7,200, and a late fee of Rs 1,800, totalling Rs 9,000.",
    "3. You are hereby called upon to pay Rs 9,000 within 15 days of receipt of this notice, failing which my client shall initiate "
    "appropriate legal proceedings for recovery, entirely at your risk as to costs.",
    "Advocate A. K. Mehra, for M/s QuickFurnish Rentals Pvt. Ltd.",
])

make("sample_offer_letter.pdf", [
    "OFFER OF EMPLOYMENT",
    "Date: 3 March 2025. To: Mr. Rahul Verma. Company: BrightAds Marketing Pvt. Ltd., Udyog Vihar, Gurugram, Haryana.",
    "Position: Senior Executive — Digital Marketing. Date of joining: 1 April 2025.",
    "Compensation: Gross monthly salary of Rs 65,000. Salary is credited on the last working day of each month.",
    "Notice period: 30 days from either side after confirmation.",
    "Full and final settlement: Dues on separation shall be settled as per applicable law and company policy.",
    "Leave: 18 days of earned leave per year; unused earned leave up to 30 days is encashable on separation.",
])
print("wrote", sorted(p.name for p in OUT.glob("*.pdf")))
