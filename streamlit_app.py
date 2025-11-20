import os, datetime as dt, random
import pandas as pd
import streamlit as st
import plotly.express as px


AUTO_PCTS = {
    "Tithe": 10,
    "Rental Reserve": 10,
    "Savings (Emergency)": 5,
    "Investing": 5,
    "Food": 10,
    "Transportation": 10,
    "Insurance/Health": 5, 
    "Child": 5, 
    "Debt": 5,
    "Clothing/Personal": 5, 
    "Subscriptions/Misc": 5, 
    "Continued Education": 5,
    "Fun/Joys/Travel": 5
    # Remaining categories get proportionally allocated
}
# ---------------------------------------
# GOOGLE SHEETS SUPPORT
# ---------------------------------------
#USE_SHEETS_DEFAULT = False  # Default checked value
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Try loading Google Sheets libraries
_gs_ok = True
try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    _gs_ok = False


def get_gspread_client_from_secrets():
    """Authenticate using Streamlit secrets (service account)."""
    if not _gs_ok:
        raise RuntimeError("gspread/google-auth not installed in environment.")

    if "gcp_service_account" not in st.secrets:
        raise RuntimeError("Missing 'gcp_service_account' in Streamlit secrets.")

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)

# ---------------------------
# CONFIG
# ---------------------------
st.set_page_config(page_title="Family Stewardship Dashboard", page_icon="📊", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Line 40 (Add the definition here)
USE_SHEETS_DEFAULT = False

# Default settings
DEFAULT_RENTAL_MONTHLY = 2500.0
DEFAULT_TITHE_PCT = 10.0
DEFAULT_SAVINGS_PCT = 10.0
DEFAULT_VACANCY_REDUCTION = 20  # %

SCRIPTURE = [
    ("Malachi 3:10", "Bring the whole tithe into the storehouse... 'Test me in this,' says the LORD Almighty."),
    ("Proverbs 21:20", "The wise store up choice food and olive oil, but fools gulp theirs down."),
    ("Luke 14:28", "Suppose one of you wants to build a tower. Won’t you first sit down and estimate the cost?"),
    ("2 Corinthians 9:7", "God loves a cheerful giver."),
    ("Philippians 4:11–12", "I have learned to be content whatever the circumstances..."),
]

CATEGORIES_DEFAULT = [
    "Tithe", "Rental Reserve", "Savings (Emergency)", "Investing", "Food",
    "Transportation", "Insurance/Health", "Child", "Debt",
    "Clothing/Personal", "Subscriptions/Misc", "Continued Education", "Fun/Joys/Travel"
]
ACCOUNTS = ["Personal", "Operations", "Business"]

# ---------------------------
# UTILITIES
# ---------------------------
def load_or_create_csv(path, columns):
    if not os.path.exists(path):
        pd.DataFrame(columns=columns).to_csv(path, index=False)
    return pd.read_csv(path)

def save_df(df, path):
    df.to_csv(path, index=False)

def csv_budget_path(account): return os.path.join(DATA_DIR, f"{account.lower()}_budgets.csv")
def csv_spend_path(account):  return os.path.join(DATA_DIR, f"{account.lower()}_spending.csv")

def ensure_budget_schema(df):
    cols = ["Category","Check1","Check2","Check3","Check4","Monthly_Total"]
    for c in cols:
        if c not in df.columns: df[c] = 0.0
    df["Monthly_Total"] = df[["Check1","Check2","Check3","Check4"]].fillna(0).sum(axis=1)
    return df[cols]

def load_income(account):
    dash_path = os.path.join(DATA_DIR,"dashboard_data.csv")
    if not os.path.exists(dash_path): return [0,0,0,0]
    df = pd.read_csv(dash_path)
    vals=[]
    for i in range(1,5):
        key=f"{account}_Check{i}_Income"
        vals.append(float(df.loc[df["Key"]==key,"Value"].iloc[0]) if key in df["Key"].values else 0)
    return vals

def save_income(account,checks):
    dash_path=os.path.join(DATA_DIR,"dashboard_data.csv")
    df=load_or_create_csv(dash_path,["Key","Value"])
    for i,v in enumerate(checks,1):
        key=f"{account}_Check{i}_Income"
        if key in df["Key"].values: df.loc[df["Key"]==key,"Value"]=v
        else: df.loc[len(df)] = [key,v]
    total=sum(checks)
    key=f"{account}_Total_Income"
    if key in df["Key"].values: df.loc[df["Key"]==key,"Value"]=total
    else: df.loc[len(df)] = [key,total]
    save_df(df,dash_path)

def show_scripture():
    verse_idx = st.session_state.get("verse_idx",0)
    ref,text = SCRIPTURE[verse_idx]
    st.markdown(f"### ✝️ “{text}”  \n*— {ref}*")
    if st.button("Next Verse 🔁", key=f"next_verse_{verse_idx}"):
        st.session_state["verse_idx"] = (verse_idx + 1) % len(SCRIPTURE)
        st.experimental_rerun()

# Default setting for Google Sheets toggle
USE_SHEETS_DEFAULT = False

# Default values so Streamlit never throws NameError
use_sheets = False
sh = None

with st.sidebar:
    st.markdown("### Data Source")
    use_sheets = st.checkbox("Use Google Sheets (optional)", value=USE_SHEETS_DEFAULT and _gs_ok)

    if use_sheets and not _gs_ok:
        st.warning("gspread/google-auth not installed. Using CSV fallback.")
        use_sheets = False

    if use_sheets:
        sheet_id = st.text_input("Google Sheet ID", value=st.secrets.get("GOOGLE_SHEET_ID", ""))

        if sheet_id:
            try:
                client = get_gspread_client_from_secrets()
                sh = client.open_by_key(sheet_id)
                st.success("Connected to Google Sheet.")
            except Exception as e:
                st.error(f"Google Sheets error: {e}")
                use_sheets = False
        else:
            st.info("Enter GOOGLE_SHEET_ID in secrets to enable Sheets.")

#--Auto-reduce budgets per category when vacancy mode is ON---#

def generate_auto_budget(check_amount, category_allocations, vacancy_mode=False, vacancy_pct=0):
    """
    Automatically allocates a check amount according to percentages.
    category_allocations: dict like {"Tithe": 10, "Savings": 5, "Food": 15}
    """
    # --- Safety 1: prevent crash on empty or zero check ---
    if check_amount is None or check_amount <= 0:
        return {cat: 0 for cat in category_allocations}

    # --- Safety 2: apply vacancy if enabled ---
    if vacancy_mode:
        check_amount = check_amount * (100 - vacancy_pct) / 100

    # --- Safety 3: prevent crash if no categories or all 0% ---
    total_pct = sum(category_allocations.values())
    if total_pct <= 0:
        return {cat: 0 for cat in category_allocations}

    # --- Compute safe allocations ---
    return {
        cat: round(check_amount * (pct / total_pct), 2)
        for cat, pct in category_allocations.items()
    }

def apply_vacancy_to_budget(budget_df, vacancy_pct):
    """Returns a copy of the budget with Monthly_Total reduced by vacancy %."""
    adj_factor = (100 - vacancy_pct) / 100
    adj_df = budget_df.copy()

    for col in ["Check1", "Check2", "Check3", "Check4"]:
        if col in adj_df.columns:
            adj_df[col] = pd.to_numeric(adj_df[col], errors="coerce").fillna(0) * adj_factor

    adj_df["Monthly_Total"] = adj_df[["Check1", "Check2", "Check3", "Check4"]].sum(axis=1)

    return adj_df

def auto_fill_budget(df, check_inputs, auto_pct_map, vacancy_mode=False, vacancy_pct=0):
    """
    Fill Check1–Check4 using percent rules (auto_pct_map) and optional vacancy.
    - df: budget df with Category, Check1..Check4
    - check_inputs: [c1, c2, c3, c4] numeric
    - auto_pct_map: {"Tithe": 10, "Savings (Emergency)": 5, ...}  (percents)
    """
    # Normalize map to only categories in df, defaulting missing to 0
    cats = list(df["Category"])
    pct_map = {c: float(auto_pct_map.get(c, 0)) for c in cats}

    # If total is 0, just set everything to 0 safely
    total_pct = sum(pct_map.values())
    if total_pct <= 0:
        for col in ["Check1","Check2","Check3","Check4"]:
            df[col] = 0.0
        df["Monthly_Total"] = 0.0
        return df

    # Normalize to 100% to avoid surprises
    scale = 100.0 / total_pct
    pct_map = {c: p * scale for c, p in pct_map.items()}

    adj = (100 - vacancy_pct) / 100.0 if vacancy_mode else 1.0

    # Allocate for each category and check
    for idx, row in df.iterrows():
        cat = row["Category"]
        pct = pct_map.get(cat, 0.0) / 100.0
        df.at[idx, "Check1"] = check_inputs[0] * pct * adj
        df.at[idx, "Check2"] = check_inputs[1] * pct * adj
        df.at[idx, "Check3"] = check_inputs[2] * pct * adj
        df.at[idx, "Check4"] = check_inputs[3] * pct * adj

    df["Monthly_Total"] = df[["Check1","Check2","Check3","Check4"]].sum(axis=1)
    return df




# ---------------------------
# MAIN APP
# ---------------------------
st.title("Family Stewardship Dashboard (Multi-Account + 4 Checks)")
st.caption("Local CSVs • Vacancy adjustments • Scripture motivation • Category management")

show_scripture()
tab1, tab2 = st.tabs(["💼 Accounts","📈 Insights"])

# ==========================================================
# TAB 1 — ACCOUNT MANAGEMENT  (DROP-IN REPLACEMENT)
# ==========================================================
with tab1:
    account = st.selectbox("Select Account", ACCOUNTS, key="acct_select")
    budget_path, spend_path = csv_budget_path(account), csv_spend_path(account)

    # Load data once
    budget_df = load_or_create_csv(
        budget_path,
        ["Category","Check1","Check2","Check3","Check4","Monthly_Total"]
    )
    budget_df = ensure_budget_schema(budget_df)

    spending_df = load_or_create_csv(
        spend_path,
        ["Date","Category","Amount","Memo"]
    )

    # Convert numeric cols once
    for c in ["Check1","Check2","Check3","Check4","Monthly_Total"]:
        if c in budget_df.columns:
            budget_df[c] = pd.to_numeric(budget_df[c], errors="coerce").fillna(0.0)
    if "Amount" in spending_df.columns:
        spending_df["Amount"] = pd.to_numeric(spending_df["Amount"], errors="coerce").fillna(0.0)

    # ✅ Header appears only once (was inside a loop before)
    st.subheader(f"{account} Overview")

    # ----------------------------
    # INCOME
    # ----------------------------
    st.markdown("### 💵 Enter This Month's Income")
    saved_checks = load_income(account)  # [c1..c4]

    c1, c2, c3, c4, c5 = st.columns(5)
    chk1 = c1.number_input("Check 1 ($)", min_value=0.0, step=100.0,
                           value=float(saved_checks[0]), key=f"{account}_chk1")
    chk2 = c2.number_input("Check 2 ($)", min_value=0.0, step=100.0,
                           value=float(saved_checks[1]), key=f"{account}_chk2")
    chk3 = c3.number_input("Check 3 ($)", min_value=0.0, step=100.0,
                           value=float(saved_checks[2]), key=f"{account}_chk3")
    chk4 = c4.number_input("Check 4 ($)", min_value=0.0, step=100.0,
                           value=float(saved_checks[3]), key=f"{account}_chk4")
    checks = [chk1, chk2, chk3, chk4]
    c5.metric("💰 Total Monthly Income", f"${sum(checks):,.2f}")

    if st.button("💾 Save Income", key=f"save_income_{account}"):
        try:
            save_income(account, checks)
            st.success("Income saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Error saving income: {e}")

    # Make total income visible in session for Tab 2
    st.session_state[f"{account}_income"] = sum(checks)

    # ----------------------------
    # VACANCY TOGGLE
    # ----------------------------
    st.markdown("### 🏠 Vacancy Adjustment Mode")
    dash_path = os.path.join(DATA_DIR, "dashboard_data.csv")
    dash_df   = load_or_create_csv(dash_path, ["Key","Value"])

    vac_key      = f"{account}_Vacancy_Mode"
    vac_pct_key  = f"{account}_Vacancy_Pct"

    saved_mode = dash_df.loc[dash_df["Key"] == vac_key, "Value"].iloc[0] if vac_key in dash_df["Key"].values else "False"
    saved_pct  = float(dash_df.loc[dash_df["Key"] == vac_pct_key, "Value"].iloc[0]) if vac_pct_key in dash_df["Key"].values else float(DEFAULT_VACANCY_REDUCTION)

    vacancy_mode = st.checkbox("Enable Vacancy (temporary income reduction)",
                               value=(saved_mode == "True"),
                               key=f"{account}_vacancy_toggle")
    vacancy_pct  = st.slider("Vacancy Reduction %", 0, 100, int(saved_pct), 5,
                              key=f"{account}_vacancy_pct")

    adj_income = sum(checks) * ((100 - vacancy_pct)/100.0) if vacancy_mode else sum(checks)
    if vacancy_mode:
        st.warning(f"Vacancy ON — income reduced {vacancy_pct}% → ${adj_income:,.2f}")
    else:
        st.info("Vacancy OFF")

    if st.button("💾 Save Vacancy Settings", key=f"save_vacancy_{account}"):
        # Persist settings
        dash_df = load_or_create_csv(dash_path, ["Key","Value"])
        for k, v in {
            vac_key: str(vacancy_mode),
            vac_pct_key: float(vacancy_pct),
            f"{account}_Adjusted_Income": float(adj_income),
        }.items():
            if k in dash_df["Key"].values:
                dash_df.loc[dash_df["Key"] == k, "Value"] = v
            else:
                dash_df.loc[len(dash_df)] = [k, v]
        save_df(dash_df, dash_path)

        # Also apply the reduction to the *current saved* budget and persist
        if vacancy_mode:
            adj_df = apply_vacancy_to_budget(budget_df, vacancy_pct)
            save_df(adj_df, budget_path)
            st.success(f"✅ Vacancy saved. Budgets reduced by {vacancy_pct}%.")
        else:
            # Save original (no reduction)
            save_df(budget_df, budget_path)
            st.success("✅ Vacancy disabled. Original budgets kept.")

        st.rerun()

    # ----------------------------
    # AUTO-BUDGET FROM PERCENTAGES (INSIDE TAB 1)
    # ----------------------------
    st.markdown("### ⚙️ Auto-Generate Budgets From Percentages")

    # Build a pct table *for the categories you actually have*.
    # Pre-fill from AUTO_PCTS; missing cats get 0.
    alloc_df = pd.DataFrame({
        "Category": budget_df["Category"],
        "Percent": [AUTO_PCTS.get(cat, 0) for cat in budget_df["Category"]]
    })
    alloc_edit = st.data_editor(
        alloc_df, hide_index=True, num_rows="dynamic",
        use_container_width=True, key=f"alloc_{account}"
    )
    alloc_map = dict(zip(alloc_edit["Category"], alloc_edit["Percent"]))

    if st.button("⚡ Generate Budgets Automatically", key=f"generate_{account}"):
        try:
            gen = auto_fill_budget(budget_df.copy(), checks, alloc_map,
                                   vacancy_mode=vacancy_mode, vacancy_pct=vacancy_pct)
            save_df(gen, budget_path)
            st.success("Budgets generated and saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Error generating budgets: {e}")

    # ----------------------------
    # BUDGET EDITOR & SPENDING
    # ----------------------------
    colA, colB = st.columns(2)

    with colA:
        st.write("### Per-Check Budgets (editable)")
        edit = st.data_editor(
            budget_df[["Category","Check1","Check2","Check3","Check4"]],
            num_rows="dynamic", use_container_width=True,
            key=f"edit_{account}"
        )
        # Apply edits and recompute total
        for c in ["Check1","Check2","Check3","Check4"]:
            budget_df[c] = pd.to_numeric(edit[c], errors="coerce").fillna(0.0)
        budget_df["Monthly_Total"] = budget_df[["Check1","Check2","Check3","Check4"]].sum(axis=1)

        st.dataframe(budget_df[["Category","Monthly_Total"]], use_container_width=True, height=260)

        if st.button("💾 Save Budgets", key=f"saveb_{account}"):
            save_df(budget_df, budget_path)
            st.success("Budgets saved.")
            st.rerun()

    with colB:
        st.write("### Actual Spending (to date)")
        totals = (spending_df.groupby("Category")["Amount"].sum()
                  .reindex(budget_df["Category"], fill_value=0)
                  .reset_index())
        st.dataframe(totals, use_container_width=True)

    # ----------------------------
    # ADD TRANSACTION
    # ----------------------------
    st.divider()
    st.subheader(f"Add Transaction ({account})")
    with st.form(f"addtxn_{account}", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        date = c1.date_input("Date", dt.date.today())
        cat  = c2.selectbox("Category", budget_df["Category"])
        amt  = c3.number_input("Amount ($)", 0.0, step=1.0)
        chk  = c4.selectbox("Check #", [1,2,3,4])
        memo = st.text_input("Memo (optional)")

        if st.form_submit_button("Add"):
            spending_df.loc[len(spending_df)] = [str(date), cat, amt, memo]
            save_df(spending_df, spend_path)
            st.success("Transaction added!")


# ==========================================================
# TAB 2 — INSIGHTS DASHBOARD
# ==========================================================
with tab2:
    st.header("📈 Financial Insights Overview")

    # Combine data
    combined, summary = pd.DataFrame(), []
    for acc in ACCOUNTS:
        b, s = csv_budget_path(acc), csv_spend_path(acc)
        bdf = ensure_budget_schema(load_or_create_csv(b,["Category","Check1","Check2","Check3","Check4","Monthly_Total"]))
        sdf = load_or_create_csv(s,["Date","Category","Amount","Memo"])
        sdf["Amount"]=pd.to_numeric(sdf["Amount"],errors="coerce").fillna(0)
        tot_b, tot_s = bdf["Monthly_Total"].sum(), sdf["Amount"].sum()
        summary.append({"Account":acc,"Total Budget":tot_b,"Total Spent":tot_s,"Remaining":tot_b-tot_s})
        if not sdf.empty:
            sdf["Account"]=acc; sdf["Date"]=pd.to_datetime(sdf["Date"],errors="coerce")
            combined=pd.concat([combined,sdf],ignore_index=True)

    # Month filter
    if not combined.empty:
        combined["Month"]=combined["Date"].dt.strftime("%B %Y")
        all_months=sorted(combined["Month"].dropna().unique(),key=lambda x:pd.to_datetime(x))
        months=st.multiselect("Select Month(s)",all_months,default=[all_months[-1]])
        combined=combined[combined["Month"].isin(months)]

    # Stewardship Ratios
    st.subheader("💒 Stewardship Ratios (10–10–70)")
    total_income=sum(st.session_state.get(f"{a}_income",0) for a in ACCOUNTS)
    st.info(f"💵 Combined Adjusted Income: ${total_income:,.2f}")
    if not combined.empty and total_income>0:
        tot=combined.groupby("Category")["Amount"].sum().to_dict()
        give=tot.get("Tithe",0)+tot.get("Giving",0)
        save_amt=tot.get("Savings (Emergency)",0)+tot.get("Investing",0)
        live=sum(v for k,v in tot.items() if k not in ["Tithe","Giving","Savings (Emergency)","Investing"])
        gp,sp,lp=[round(100*x/total_income,1) for x in [give,save_amt,live]]
        c1,c2,c3=st.columns(3)
        c1.metric("🙏 Giving (Goal 10%)",f"{gp}%")
        c2.metric("💰 Saving/Investing (Goal 10%)",f"{sp}%")
        c3.metric("🏡 Living (Goal 70%)",f"{lp}%")
        st.progress(min(1,(gp+sp+lp)/100),text=f"Giving {gp}% • Saving {sp}% • Living {lp}%")

    # Budget vs Actual + Over/Under
    if summary:
        df=pd.DataFrame(summary)
        st.subheader("📊 Budget vs Actual by Account")
        fig=px.bar(df.melt(id_vars="Account",value_vars=["Total Budget","Total Spent"]),
                   x="Account",y="value",color="variable",barmode="group")
        st.plotly_chart(fig,use_container_width=True)
        df["Status"]=df["Remaining"].apply(lambda v:"✅ Under" if v>=0 else "⚠️ Over")
        st.dataframe(df,use_container_width=True)

    # Spending breakdowns
    if not combined.empty:
        st.subheader("🍰 Spending Breakdown")
        pie=px.pie(combined,names="Category",values="Amount",hole=0.4)
        st.plotly_chart(pie,use_container_width=True)
        trend=(combined.groupby(["Month","Account"])["Amount"].sum().reset_index())
        bar=px.bar(trend,x="Month",y="Amount",color="Account",barmode="group")
        st.plotly_chart(bar,use_container_width=True)

    # Monthly Summary
    if summary:
        st.subheader("🧾 Monthly Summary (Combined)")
        total_budget=sum(d["Total Budget"] for d in summary)
        total_spent=sum(d["Total Spent"] for d in summary)
        rem=total_budget-total_spent
        c1,c2,c3=st.columns(3)
        c1.metric("Total Budget",f"${total_budget:,.0f}")
        c2.metric("Total Spent",f"${total_spent:,.0f}")
        c3.metric("Remaining",f"${rem:,.0f}")
