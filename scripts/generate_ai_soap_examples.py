"""Generate AI SOAP example notes for local dev/test seeding.

We keep these notes:
- Clinically plausible but synthetic
- Free of direct PHI (no real names, DOBs, addresses, MRNs)
- Consistent in format (SOAP) so the parser has meaningful coverage

This script writes files into /data/exampleFiles with the prefix `ai_generated_`.
"""

from __future__ import annotations

from pathlib import Path


def _render_note(*, idx: int, title: str, s: str, o: str, a: str, p: str) -> str:
    return (
        f"SOAP Note - Synthetic Example #{idx:03d}\n"
        f"Title: {title}\n\n"
        f"S:\n{s.strip()}\n\n"
        f"O:\n{o.strip()}\n\n"
        f"A:\n{a.strip()}\n\n"
        f"P:\n{p.strip()}\n"
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "data" / "exampleFiles"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases: list[tuple[str, str, str, str, str]] = [
        (
            "Annual preventive visit",
            "Here for annual wellness visit. No acute complaints. Exercises 2-3x/week. Diet mixed. "
            "Denies chest pain, dyspnea, syncope, focal weakness. No tobacco; rare alcohol.",
            "Vitals: BP 126/78, HR 72, RR 16, Temp 98.2F, BMI 27.1.\n"
            "Gen: Alert, NAD.\nCV: RRR, no murmurs.\nResp: CTA bilat.\nAbd: Soft, NT.\n"
            "Screening labs ordered: CBC, CMP, lipid panel.",
            "Well adult exam.\nOverweight (BMI 27).\nCardiometabolic risk screening.",
            "Lifestyle counseling: Mediterranean-style diet, 150 min/wk moderate exercise.\n"
            "Review labs when resulted; follow up 6-12 months or sooner PRN.",
        ),
        (
            "Upper respiratory symptoms",
            "Cough and sore throat x4 days. Rhinorrhea, mild fatigue. Denies shortness of breath or "
            "chest pain. No GI symptoms. Home COVID test negative yesterday.",
            "Vitals: BP 118/74, HR 84, RR 18, Temp 99.1F, SpO2 98% RA.\n"
            "HEENT: Mild pharyngeal erythema, no exudate. Lungs CTA.\n",
            "Viral URI.\nRule out strep low probability.",
            "Supportive care: fluids, rest, honey/tea, acetaminophen/ibuprofen PRN.\n"
            "Return precautions for persistent fever, dyspnea, worsening symptoms >7-10 days.",
        ),
        (
            "Hypertension follow-up",
            "Follow-up for elevated home BP readings. Reports occasional headaches, no vision changes. "
            "Adherence to low-salt diet inconsistent.",
            "Vitals: BP 146/92, HR 76, BMI 29.0.\n"
            "Exam: no edema; CV/resp normal.\n",
            "Stage 2 hypertension (uncontrolled).\nLifestyle factors contributing.",
            "Start amlodipine 5 mg PO daily; discuss side effects.\n"
            "Home BP log; low-salt diet; follow up in 4 weeks.\n"
            "BMP in 2-4 weeks if additional meds added later.",
        ),
        (
            "Type 2 diabetes follow-up",
            "Routine DM2 follow-up. Reports improved diet; occasional post-meal glucose spikes. "
            "No hypoglycemia. Denies neuropathy symptoms.",
            "Vitals: BP 132/80, HR 70, BMI 31.2.\n"
            "Foot exam: intact sensation, no ulcers.\nPOC A1c 7.4%.\n",
            "Type 2 diabetes, above goal.\nObesity.",
            "Increase metformin to 1000 mg BID if tolerated.\n"
            "Nutrition referral; consider GLP-1 RA discussion next visit.\n"
            "Repeat A1c in 3 months.",
        ),
        (
            "Low back pain",
            "Low back pain x1 week after lifting. No trauma. No weakness, numbness, bowel/bladder changes.",
            "Vitals stable. Back: paraspinal tenderness, no midline tenderness. Neuro: 5/5 strength, "
            "sensation intact, negative straight leg raise.\n",
            "Acute mechanical low back pain.\nNo red flags.",
            "NSAIDs PRN with food; heat; gentle stretching.\n"
            "Avoid heavy lifting 1-2 weeks. PT if not improving in 2-3 weeks.\n"
            "Return precautions for neurologic deficits or bowel/bladder symptoms.",
        ),
        (
            "Dysuria",
            "Burning with urination and urinary frequency x2 days. No flank pain. No fever/chills. "
            "No vaginal discharge.",
            "Vitals: Temp 98.6F. Abd: mild suprapubic tenderness, no CVA tenderness.\n"
            "UA dip: +LE, +nitrite.\n",
            "Uncomplicated cystitis.",
            "Empiric antibiotics per local guideline; hydration.\n"
            "Urine culture sent. Return precautions for fever, flank pain, worsening symptoms.",
        ),
        (
            "Anxiety symptoms",
            "Reports excessive worry and insomnia x2 months. Difficulty concentrating. Denies SI/HI. "
            "No substance use.",
            "Vitals stable. Mental status: cooperative, linear thought process, appropriate affect.\n",
            "Generalized anxiety symptoms.\nInsomnia.",
            "Discuss CBT resources; sleep hygiene.\n"
            "Consider SSRI trial; shared decision-making.\n"
            "Follow up in 4-6 weeks; sooner if worsening.",
        ),
        (
            "Asthma check",
            "Asthma follow-up. Uses rescue inhaler ~3x/week. Nighttime symptoms 1x/week. "
            "Triggers: cold air and exercise.",
            "Vitals: SpO2 97% RA. Lungs: mild end-expiratory wheeze.\n",
            "Asthma, not well controlled.",
            "Start low-dose ICS daily; review inhaler technique.\n"
            "Rescue inhaler PRN. Peak flow log. Follow up in 6-8 weeks.",
        ),
        (
            "Skin rash",
            "Itchy rash on forearms x1 week after new detergent. No fever. No mucosal involvement.",
            "Skin: erythematous, mildly scaly patches on bilateral forearms, no vesicles.\n",
            "Contact dermatitis.",
            "Stop suspected irritant; topical steroid BID x7-10 days.\n"
            "Antihistamine PRN itching. Return if spreading or signs of infection.",
        ),
        (
            "Knee pain",
            "Anterior knee pain with stairs x3 weeks. No locking/giving way. No trauma.",
            "Vitals stable. Knee: no effusion, mild patellar tenderness, full ROM, stable ligaments.\n",
            "Patellofemoral pain syndrome.",
            "Activity modification; PT exercises focusing on quad/hip strengthening.\n"
            "NSAIDs PRN. Follow up 6 weeks if persistent.",
        ),
    ]

    total = 45
    for i in range(1, total + 1):
        title, s, o, a, p = cases[(i - 1) % len(cases)]
        # small deterministic variation without PHI
        note = _render_note(
            idx=i,
            title=title,
            s=s,
            o=o,
            a=a,
            p=p,
        )
        path = out_dir / f"ai_generated_soap_{i:03d}.txt"
        path.write_text(note, encoding="utf-8")

    print(f"Wrote {total} files to {out_dir}")


if __name__ == "__main__":
    main()


