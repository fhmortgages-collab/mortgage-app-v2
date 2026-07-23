import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

st.set_page_config(page_title="Canadian Debt Servicing Calculator", page_icon="🏠", layout="wide")

st.title("🏠 Canadian Mortgage Underwriting Engine")
st.caption("Includes RBC Retail Credit Policy (GRR20 / PBR 001) & OSFI Guideline B-20 Standards")
st.divider()

# --- GEMINI AI EXTRACTOR ---
class IncomeExtraction(BaseModel):
    gross_annual_income: float = Field(description="Gross annual income from T4, NOA, or paystub.")
    document_type: str = Field(description="T4, NOA, or Paystub")

def extract_income(image_bytes, api_key: str) -> IncomeExtraction:
    client = genai.Client(api_key=api_key)
    prompt = "Extract gross annual income (Line 15000 / Box 14) from this document. Respond strictly with JSON."
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
            prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=IncomeExtraction,
            temperature=0.0
        )
    )
    return IncomeExtraction.parse_raw(response.text)

# --- MORTGAGE CALCULATION ENGINE ---
def calc_annual_p_and_i(loan: float, rate_pct: float, years: int) -> float:
    rate = rate_pct / 100.0
    eff_monthly_rate = (1.0 + rate / 2.0)**(2.0 / 12.0) - 1.0
    n = years * 12
    monthly = loan * (eff_monthly_rate * (1 + eff_monthly_rate)**n) / ((1 + eff_monthly_rate)**n - 1)
    return monthly * 12.0

# --- SIDEBAR: DOCUMENT EXTRACTION ---
st.sidebar.header("📂 1. Document Extraction")
gemini_key = st.sidebar.text_input("Gemini API Key (Optional)", type="password")
uploaded_file = st.sidebar.file_uploader("Upload T4, NOA, or Paystub", type=["jpg", "jpeg", "png"])

extracted_income = None
if uploaded_file and gemini_key:
    if st.sidebar.button("Scan Document"):
        try:
            res = extract_income(uploaded_file.getvalue(), gemini_key)
            extracted_income = res.gross_annual_income
            st.sidebar.success(f"Found: ${extracted_income:,.2f}")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

st.sidebar.divider()

# --- SIDEBAR: BORROWER & PROPERTY INPUTS ---
st.sidebar.header("📊 2. Borrower & Property Inputs")
default_inc = float(extracted_income) if extracted_income else 140000.0
gross_annual_income = st.sidebar.number_input("Eligible Annual Gross Income ($)", min_value=1.0, value=default_inc, step=5000.0)
loan_amount = st.sidebar.number_input("Mortgage Loan Amount ($)", min_value=1.0, value=650000.0, step=10000.0)
contract_rate = st.sidebar.number_input("Contract Rate (%)", min_value=0.1, max_value=15.0, value=4.25, step=0.05)
amortization_years = st.sidebar.slider("Amortization (Years)", min_value=5, max_value=30, value=25)

st.sidebar.subheader("Property Expenses (Annual)")
annual_tax = st.sidebar.number_input("Property Tax ($)", min_value=0.0, value=4800.0)
annual_heat = st.sidebar.number_input("Heating Cost ($) [Std: $1,200]", min_value=0.0, value=1200.0)
annual_condo = st.sidebar.number_input("Condo Fees ($)", min_value=0.0, value=2400.0)
is_investor = st.sidebar.checkbox("Non-Owner Occupied / Investment Property (100% Condo Fees)", value=False)

condo_factor = 1.0 if is_investor else 0.50
pith_c_expenses = annual_tax + annual_heat + (condo_factor * annual_condo)

# --- DEBT OBLIGATIONS INPUTS (RBC POLICY) ---
st.sidebar.divider()
st.sidebar.header("💳 3. Existing Obligations (RBC Policy)")
is_quebec = st.sidebar.checkbox("Quebec Resident (Credit Card Rules: 5%)", value=False)

st.sidebar.markdown("**Credit Cards & Revolving Lines**")
cc_balance = st.sidebar.number_input("Credit Card Balance ($)", min_value=0.0, value=5000.0)
loc_balance = st.sidebar.number_input("Unsecured LOC Balance ($)", min_value=0.0, value=10000.0)

st.sidebar.markdown("**Installment Loans / Leases**")
inst_monthly = st.sidebar.number_input("Installment Loan Monthly Payment ($)", min_value=0.0, value=350.0)
inst_balance = st.sidebar.number_input("Installment Loan Outstanding Balance ($)", min_value=0.0, value=15000.0)

st.sidebar.markdown("**Other Obligations**")
other_monthly = st.sidebar.number_input("Support / CRA Payments / Other Monthly ($)", min_value=0.0, value=0.0)

# --- CALCULATE MONTHLY CARRYING COSTS ---
cc_rate = 0.05 if is_quebec else 0.03
monthly_cc = cc_balance * cc_rate
monthly_loc = loc_balance * 0.03
monthly_inst = inst_monthly if inst_monthly > 0 else (inst_balance * 0.02)

total_annual_debt = (monthly_cc + monthly_loc + monthly_inst + other_monthly) * 12.0

# --- UNDERWRITING CALCULATIONS ---
actual_p_i = calc_annual_p_and_i(loan_amount, contract_rate, amortization_years)
actual_gds = ((actual_p_i + pith_c_expenses) / gross_annual_income) * 100.0
actual_tds = ((actual_p_i + pith_c_expenses + total_annual_debt) / gross_annual_income) * 100.0

qual_rate = max(5.25, contract_rate + 2.0)
qual_p_i = calc_annual_p_and_i(loan_amount, qual_rate, amortization_years)
qual_gds = ((qual_p_i + pith_c_expenses) / gross_annual_income) * 100.0
qual_tds = ((qual_p_i + pith_c_expenses + total_annual_debt) / gross_annual_income) * 100.0

std_gds_pass = qual_gds <= 32.0
std_tds_pass = qual_tds <= 40.0
max_gds_pass = qual_gds <= 39.0
max_tds_pass = qual_tds <= 44.0

# --- MAIN DISPLAY ---
st.subheader("📋 RBC Debt Carrying Cost Breakdown")
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Credit Card Monthly", f"${monthly_cc:,.2f}", f"{'5%' if is_quebec else '3%'} of balance")
col_b.metric("Line of Credit Monthly", f"${monthly_loc:,.2f}", "3% of balance")
col_c.metric("Installment Loan Monthly", f"${monthly_inst:,.2f}", "Actual / 2% fallback")
col_d.metric("Total Monthly Obligations", f"${(total_annual_debt / 12.0):,.2f}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("💵 Actual Out-of-Pocket Cash Flow")
    st.caption(f"Contract Rate: **{contract_rate:.2f}%** | P&I: **${(actual_p_i/12):,.2f}/mo**")
    m1, m2 = st.columns(2)
    m1.metric("Actual GDS", f"{actual_gds:.2f}%")
    m2.metric("Actual TDS", f"{actual_tds:.2f}%")
    st.markdown(f"* **Annual Housing Cost [PITH+C]:** `${(actual_p_i + pith_c_expenses):,.2f}`")

with col2:
    st.subheader("🏛️ Stress Test (OSFI B-20 / RBC Policy)")
    st.caption(f"Qualifying Rate: **{qual_rate:.2f}%** | P&I: **${(qual_p_i/12):,.2f}/mo**")
    m3, m4 = st.columns(2)
    m3.metric("Qualifying GDS", f"{qual_gds:.2f}%", 
              delta="Standard (≤32%)" if std_gds_pass else ("Max Limit (≤39%)" if max_gds_pass else "Exceeds 39%"), 
              delta_color="normal" if max_gds_pass else "inverse")
    m4.metric("Qualifying TDS", f"{qual_tds:.2f}%", 
              delta="Standard (≤40%)" if std_tds_pass else ("Max Limit (≤44%)" if max_tds_pass else "Exceeds 44%"), 
              delta_color="normal" if max_tds_pass else "inverse")
    st.markdown(f"* **Qualifying Housing Cost [PITH+C]:** `${(qual_p_i + pith_c_expenses):,.2f}`")

st.divider()

if std_gds_pass and std_tds_pass:
    st.success("✅ **DECISION: APPROVED (Standard Policy)** — GDS ≤ 32% and TDS ≤ 40%.")
elif max_gds_pass and max_tds_pass:
    st.warning("⚠️ **DECISION: REQUIRES BUSINESS CASE / EXCEPTION** — Exceeds standard 32/40 limits but within max thresholds (GDS ≤ 39%, TDS ≤ 44%). Exception rationale required.")
else:
    st.error("❌ **DECISION: DECLINED** — Exceeds maximum allowable debt service limits.")
