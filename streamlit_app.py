import os, datetime as dt, random
import pandas as pd
import streamlit as st
import plotly.express as px

# ---------------------------
# CONFIG
# ---------------------------
st.set_page_config(page_title="Family Stewardship Dashboard", page_icon="📊", layout="wide")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

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

# ---------------------------
# MAIN APP
# ---------------------------
st.title("Family Stewardship Dashboard (Multi-Account + 4 Checks)")
st.caption("Local CSVs • Vacancy adjustments • Scripture motivation • Category management")

show_scripture()
tab1, tab2 = st.tabs(["💼 Accounts","📈 Insights"])

# ==========================================================
# TAB 1 — ACCOUNT MANAGEMENT
# ==========================================================
with tab1:
    account = st.selectbox("Select Account", ACCOUNTS)
    budget_path, spend_path = csv_budget_path(account), csv_spend_path(account)

    budget_df = load_or_create_csv(budget_path,["Category","Check1","Check2","Check3","Check4","Monthly_Total"])
    budget_df = ensure_budget_schema(budget_df)
    spending_df = load_or_create_csv(spend_path,["Date","Category","Amount","Memo"])
    for c in ["Amount","Check1","Check2","Check3","Check4","Monthly_Total"]:
        if c in budget_df.columns: budget_df[c]=pd.to_numeric(budget_df[c],errors="coerce").fillna(0)

    st.subheader(f"{account} Overview")

    # -----------------------------
    # 💵 PER-CHECK INCOME + VACANCY
    # -----------------------------
    st.markdown("### 💵 Enter This Month's Income")
    check_vals = [float(v) for v in load_income(account)]
    c1, c2, c3, c4, c5 = st.columns(5)
    checks = [
        c1.number_input("Check 1 ($)", min_value=0.0, step=100.0, value=float(check_vals[0]), key=f"{account}_c1"),
        c2.number_input("Check 2 ($)", min_value=0.0, step=100.0, value=float(check_vals[1]), key=f"{account}_c2"),
        c3.number_input("Check 3 ($)", min_value=0.0, step=100.0, value=float(check_vals[2]), key=f"{account}_c3"),
        c4.number_input("Check 4 ($)", min_value=0.0, step=100.0, value=float(check_vals[3]), key=f"{account}_c4")
    ]
    total_income = sum(checks)
    c5.metric("💰 Total Monthly Income", f"${total_income:,.2f}")

    if st.button("💾 Save Income", key=f"save_income_{account}"):
        save_income(account, checks, use_sheets, sh)
        st.success("Income saved and synced!")

    # -----------------------------
    # 🏠 VACANCY MODE ADJUSTMENT
    # -----------------------------
    st.markdown("### 🏠 Vacancy Adjustment Mode")

    # Load persisted vacancy setting
    dash_path = os.path.join(DATA_DIR, "dashboard_data.csv")
    dash_df = load_or_create_csv(dash_path, ["Key", "Value"])
    vacancy_key = f"{account}_Vacancy_Mode"
    vacancy_pct_key = f"{account}_Vacancy_Pct"

    vacancy_mode = st.checkbox("Enable Vacancy Mode (temporary income reduction)", value=False, key=f"{account}_vacancy_toggle")
    vacancy_pct = float(
        dash_df.loc[dash_df["Key"] == vacancy_pct_key, "Value"].iloc[0]
    ) if vacancy_pct_key in dash_df["Key"].values else 20.0

    if vacancy_mode:
        vacancy_pct = st.slider("Vacancy Reduction %", 0, 100, int(vacancy_pct), 5, key=f"{account}_vacancy_pct")
        adj_factor = (100 - vacancy_pct) / 100
        adjusted_income = total_income * adj_factor
        st.warning(f"Vacancy mode ON — reducing total income by {vacancy_pct}% → New Total: ${adjusted_income:,.2f}")
    else:
        adjusted_income = total_income

    # Persist settings (local or Google Sheets)
    if st.button("💾 Save Vacancy Settings", key=f"save_vacancy_{account}"):
        if use_sheets and sh is not None:
            ws_dash = open_or_create_ws(sh, "Dashboard_Data", ["Key", "Value"])
            ws_dash.update(f"A1:B1", [["Key", "Value"]])
            rows = ws_dash.get_all_values()
            df_dash = pd.DataFrame(rows[1:], columns=rows[0]) if len(rows) > 1 else pd.DataFrame(columns=["Key", "Value"])
            updates = {
                vacancy_key: str(vacancy_mode),
                vacancy_pct_key: vacancy_pct,
                f"{account}_Adjusted_Income": adjusted_income,
            }
            for k, v in updates.items():
                if k in df_dash["Key"].values:
                    ws_dash.update_cell(df_dash.index[df_dash["Key"] == k][0] + 2, 2, v)
                else:
                    ws_dash.append_row([k, v])
        else:
            for k, v in {
                vacancy_key: str(vacancy_mode),
                vacancy_pct_key: vacancy_pct,
                f"{account}_Adjusted_Income": adjusted_income,
            }.items():
                if k in dash_df["Key"].values:
                    dash_df.loc[dash_df["Key"] == k, "Value"] = v
                else:
                    dash_df.loc[len(dash_df)] = [k, v]
            save_df(dash_df, dash_path)
        st.success("Vacancy settings saved!")

    # Apply adjustment globally for current session
    st.session_state[f"{account}_adjusted_income"] = adjusted_income
    st.session_state[f"{account}_vacancy_mode"] = vacancy_mode
    st.session_state[f"{account}_vacancy_pct"] = vacancy_pct


    # -----------------------------
    # BUDGET EDITOR & SPENDING
    # -----------------------------
    colA,colB = st.columns(2)
    with colA:
        st.write("### Per-Check Budgets")
        edit = st.data_editor(budget_df[["Category","Check1","Check2","Check3","Check4"]],num_rows="dynamic",use_container_width=True,key=f"edit_{account}")
        for c in ["Check1","Check2","Check3","Check4"]:
            budget_df[c]=pd.to_numeric(edit[c],errors="coerce").fillna(0)
        budget_df["Monthly_Total"]=budget_df[["Check1","Check2","Check3","Check4"]].sum(axis=1)
        st.dataframe(budget_df[["Category","Monthly_Total"]],use_container_width=True)
        if st.button("💾 Save Budgets",key=f"saveb_{account}"):
            save_df(budget_df,budget_path)
            st.success("Budgets saved locally.")

    with colB:
        st.write("### Actual Spending (to date)")
        spending_df["Amount"]=pd.to_numeric(spending_df.get("Amount",0),errors="coerce").fillna(0)
        totals=spending_df.groupby("Category")["Amount"].sum().reindex(budget_df["Category"],fill_value=0).reset_index()
        st.dataframe(totals,use_container_width=True)

    # -----------------------------
    # ADD TRANSACTION
    # -----------------------------
    st.divider()
    st.subheader(f"Add Transaction ({account})")
    with st.form(f"addtxn_{account}",clear_on_submit=True):
        c1,c2,c3,c4=st.columns(4)
        date=c1.date_input("Date",dt.date.today())
        cat=c2.selectbox("Category",budget_df["Category"])
        amt=c3.number_input("Amount ($)",0.0,step=1.0)
        chk=c4.selectbox("Check #", [1,2,3,4])
        memo=st.text_input("Memo (optional)")
        if st.form_submit_button("Add"):
            spending_df.loc[len(spending_df)] = [str(date),cat,amt,memo]
            save_df(spending_df,spend_path)
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