import sqlite3
from datetime import date
import pandas as pd
import streamlit as st

DB_PATH = "navratri_hisab.db"
DAYS = list(range(1, 10))
CATEGORIES = ["Pass", "Water Bottle", "Food", "Petrol", "Parking", "Other"]


# ---------------------------- Database setup ----------------------------
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS day_participants (
                day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 9),
                person_id INTEGER NOT NULL,
                PRIMARY KEY(day, person_id),
                FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 9),
                category TEXT NOT NULL,
                description TEXT DEFAULT '',
                amount REAL NOT NULL CHECK(amount >= 0),
                paid_by INTEGER,
                expense_date TEXT,
                FOREIGN KEY(paid_by) REFERENCES people(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                deposit_date TEXT,
                note TEXT DEFAULT '',
                FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
            );
            """
        )


def read_df(query, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_people():
    return read_df("SELECT id, name FROM people ORDER BY name")


def money(value):
    return f"₹{float(value):,.2f}"


def main():
    st.set_page_config(
        page_title="Navratri Hisab",
        page_icon="🪔",
        layout="wide",
    )
    init_db()

    st.title("🪔 Navratri Hisab — 9 Days Expense Manager")
    st.caption(
        "Track day-wise expenses, split each day's cost only among that day's participants, "
        "record deposits, and calculate each person's final balance."
    )

    people = get_people()
    tabs = st.tabs(
        ["📊 Summary", "👥 People & Participants", "➕ Add Expense", "💰 Deposits", "📅 Day-wise Details", "🗂️ Manage Data"]
    )

    # ---------------------------- Summary ----------------------------
    with tabs[0]:
        people = get_people()
        expenses = read_df(
            """SELECT e.id, e.day, e.category, e.description, e.amount,
                      e.paid_by, p.name AS paid_by_name
               FROM expenses e LEFT JOIN people p ON p.id = e.paid_by
               ORDER BY e.day, e.id"""
        )
        deposits = read_df(
            """SELECT d.person_id, p.name, d.amount
               FROM deposits d JOIN people p ON p.id = d.person_id"""
        )
        participants = read_df(
            """SELECT dp.day, dp.person_id, p.name
               FROM day_participants dp JOIN people p ON p.id = dp.person_id"""
        )

        total_expenses = float(expenses["amount"].sum()) if not expenses.empty else 0.0
        total_deposits = float(deposits["amount"].sum()) if not deposits.empty else 0.0
        st_cols = st.columns(3)
        st_cols[0].metric("Total Expenses", money(total_expenses))
        st_cols[1].metric("Total Deposits", money(total_deposits))
        st_cols[2].metric("People Added", len(people))

        if people.empty:
            st.info("First, add people in the **People & Participants** tab.")
        else:
            # Cost per person is calculated separately for each day, based only on
            # the participants registered for that day.
            share_by_person = {int(row.id): 0.0 for row in people.itertuples()}
            for day in DAYS:
                day_total = (
                    float(expenses.loc[expenses["day"] == day, "amount"].sum())
                    if not expenses.empty else 0.0
                )
                day_people = (
                    participants.loc[participants["day"] == day, "person_id"].tolist()
                    if not participants.empty else []
                )
                if day_people:
                    share = day_total / len(day_people)
                    for pid in day_people:
                        share_by_person[int(pid)] = share_by_person.get(int(pid), 0.0) + share

            deposit_by_person = (
                deposits.groupby("person_id")["amount"].sum().to_dict()
                if not deposits.empty else {}
            )
            paid_by_person = {}
            if not expenses.empty:
                paid_rows = expenses.dropna(subset=["paid_by"])
                if not paid_rows.empty:
                    paid_by_person = paid_rows.groupby("paid_by")["amount"].sum().to_dict()

            summary_rows = []
            for person in people.itertuples():
                pid = int(person.id)
                person_share = share_by_person.get(pid, 0.0)
                deposited = float(deposit_by_person.get(pid, 0.0))
                paid_directly = float(paid_by_person.get(pid, 0.0))
                # Positive = this person has paid more than their share; negative = they owe.
                balance = deposited + paid_directly - person_share
                attended_days = (
                    sorted(participants.loc[participants["person_id"] == pid, "day"].tolist())
                    if not participants.empty else []
                )
                summary_rows.append(
                    {
                        "Person": person.name,
                        "Days Attended": ", ".join(map(str, attended_days)) if attended_days else "—",
                        "Expense Share": round(person_share, 2),
                        "Deposited": round(deposited, 2),
                        "Paid Expenses Directly": round(paid_directly, 2),
                        "Balance (+ receive / - pay)": round(balance, 2),
                    }
                )
            summary_df = pd.DataFrame(summary_rows)
            st.subheader("Final person-wise settlement")
            st.caption(
                "Positive balance = money to receive back. Negative balance = amount still to pay. "
                "This calculation assumes deposits are contributions to the group and listed expenses "
                "were paid directly by the selected person, not from the deposit pool."
            )
            st.dataframe(
                summary_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Expense Share": st.column_config.NumberColumn(format="₹%.2f"),
                    "Deposited": st.column_config.NumberColumn(format="₹%.2f"),
                    "Paid Expenses Directly": st.column_config.NumberColumn(format="₹%.2f"),
                    "Balance (+ receive / - pay)": st.column_config.NumberColumn(format="₹%.2f"),
                },
            )
            csv = summary_df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download person-wise summary (CSV)", csv, "navratri_summary.csv", "text/csv")

            st.subheader("Day-wise totals")
            day_rows = []
            for day in DAYS:
                day_expenses = expenses.loc[expenses["day"] == day] if not expenses.empty else pd.DataFrame()
                total = float(day_expenses["amount"].sum()) if not day_expenses.empty else 0.0
                day_names = (
                    participants.loc[participants["day"] == day, "name"].tolist()
                    if not participants.empty else []
                )
                day_rows.append(
                    {
                        "Day": f"Day {day}",
                        "Participants": ", ".join(day_names) if day_names else "No participants set",
                        "People Count": len(day_names),
                        "Total Expense": round(total, 2),
                        "Per Person": round(total / len(day_names), 2) if day_names else 0.0,
                    }
                )
            st.dataframe(pd.DataFrame(day_rows), use_container_width=True, hide_index=True)

    # ---------------------------- People and participants ----------------------------
    with tabs[1]:
        st.subheader("Add a person")
        with st.form("add_person_form", clear_on_submit=True):
            new_name = st.text_input("Person's name", placeholder="e.g. Dhruv")
            add_person = st.form_submit_button("Add Person")
        if add_person:
            clean_name = new_name.strip()
            if not clean_name:
                st.error("Please enter a name.")
            else:
                try:
                    with get_connection() as conn:
                        conn.execute("INSERT INTO people(name) VALUES (?)", (clean_name,))
                    st.success(f"{clean_name} added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.warning("This person is already in the list.")

        people = get_people()
        st.subheader("People list")
        if people.empty:
            st.info("No people added yet.")
        else:
            st.dataframe(people[["name"]].rename(columns={"name": "Person"}), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Choose who attended each day")
            st.caption("Only the people selected for a particular day will share that day's expenses.")
            chosen_day = st.selectbox("Select day", DAYS, format_func=lambda d: f"Day {d}", key="participants_day")
            existing_ids = read_df(
                "SELECT person_id FROM day_participants WHERE day = ?", (chosen_day,)
            )["person_id"].tolist()
            name_to_id = dict(zip(people["name"], people["id"]))
            existing_names = [name for name, pid in name_to_id.items() if int(pid) in existing_ids]
            with st.form(f"participants_form_{chosen_day}"):
                selected_names = st.multiselect(
                    f"Participants for Day {chosen_day}",
                    options=people["name"].tolist(),
                    default=existing_names,
                )
                save_participants = st.form_submit_button("Save Participants")
            if save_participants:
                selected_ids = [int(name_to_id[name]) for name in selected_names]
                with get_connection() as conn:
                    conn.execute("DELETE FROM day_participants WHERE day = ?", (chosen_day,))
                    conn.executemany(
                        "INSERT INTO day_participants(day, person_id) VALUES (?, ?)",
                        [(chosen_day, pid) for pid in selected_ids],
                    )
                st.success(f"Saved {len(selected_ids)} participant(s) for Day {chosen_day}.")
                st.rerun()

    # ---------------------------- Add expense ----------------------------
    with tabs[2]:
        people = get_people()
        st.subheader("Record an expense")
        if people.empty:
            st.warning("Add people first. You can also record expenses without a payer later from Manage Data.")
        with st.form("expense_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            day = c1.selectbox("Navratri day", DAYS, format_func=lambda d: f"Day {d}")
            category = c2.selectbox("Expense category", CATEGORIES)
            description = st.text_input("Description (optional)", placeholder="e.g. 5 passes, dinner, petrol")
            c3, c4 = st.columns(2)
            amount = c3.number_input("Amount (₹)", min_value=0.0, step=10.0, format="%.2f")
            expense_date = c4.date_input("Date", value=date.today())
            payer_options = ["Not specified"] + (people["name"].tolist() if not people.empty else [])
            paid_by_name = st.selectbox("Who paid this expense?", payer_options)
            save_expense = st.form_submit_button("Save Expense")
        if save_expense:
            if amount <= 0:
                st.error("Enter an amount greater than ₹0.")
            else:
                payer_id = None
                if paid_by_name != "Not specified":
                    payer_id = int(people.loc[people["name"] == paid_by_name, "id"].iloc[0])
                with get_connection() as conn:
                    conn.execute(
                        """INSERT INTO expenses(day, category, description, amount, paid_by, expense_date)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (day, category, description.strip(), float(amount), payer_id, expense_date.isoformat()),
                    )
                st.success(f"Expense of {money(amount)} saved for Day {day}.")
                st.rerun()

    # ---------------------------- Deposits ----------------------------
    with tabs[3]:
        people = get_people()
        st.subheader("Record a deposit / contribution")
        if people.empty:
            st.info("Add people first.")
        else:
            with st.form("deposit_form", clear_on_submit=True):
                person_name = st.selectbox("Person", people["name"].tolist())
                deposit_amount = st.number_input("Deposit amount (₹)", min_value=0.0, step=100.0, format="%.2f")
                deposit_date = st.date_input("Deposit date", value=date.today())
                note = st.text_input("Note (optional)", placeholder="e.g. advance contribution")
                save_deposit = st.form_submit_button("Save Deposit")
            if save_deposit:
                if deposit_amount <= 0:
                    st.error("Enter a deposit amount greater than ₹0.")
                else:
                    pid = int(people.loc[people["name"] == person_name, "id"].iloc[0])
                    with get_connection() as conn:
                        conn.execute(
                            "INSERT INTO deposits(person_id, amount, deposit_date, note) VALUES (?, ?, ?, ?)",
                            (pid, float(deposit_amount), deposit_date.isoformat(), note.strip()),
                        )
                    st.success(f"Deposit of {money(deposit_amount)} recorded for {person_name}.")
                    st.rerun()

            deposits_df = read_df(
                """SELECT d.id AS ID, p.name AS Person, d.amount AS Amount,
                          d.deposit_date AS Date, d.note AS Note
                   FROM deposits d JOIN people p ON p.id = d.person_id
                   ORDER BY d.deposit_date DESC, d.id DESC"""
            )
            st.subheader("Deposit history")
            if deposits_df.empty:
                st.info("No deposits recorded yet.")
            else:
                st.dataframe(
                    deposits_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Amount": st.column_config.NumberColumn(format="₹%.2f")},
                )

    # ---------------------------- Day-wise details ----------------------------
    with tabs[4]:
        selected_day = st.selectbox("View day", DAYS, format_func=lambda d: f"Day {d}", key="detail_day")
        day_expenses = read_df(
            """SELECT e.id AS ID, e.category AS Category, e.description AS Description,
                      e.amount AS Amount, COALESCE(p.name, 'Not specified') AS Paid_By,
                      e.expense_date AS Date
               FROM expenses e LEFT JOIN people p ON p.id = e.paid_by
               WHERE e.day = ? ORDER BY e.id""",
            (selected_day,),
        )
        selected_participants = read_df(
            """SELECT p.name FROM day_participants dp
               JOIN people p ON p.id = dp.person_id
               WHERE dp.day = ? ORDER BY p.name""",
            (selected_day,),
        )
        total = float(day_expenses["Amount"].sum()) if not day_expenses.empty else 0.0
        count = len(selected_participants)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total expense", money(total))
        c2.metric("Participants", count)
        c3.metric("Expense per person", money(total / count if count else 0))
        st.write("**Participants:**", ", ".join(selected_participants["name"].tolist()) if count else "No participants selected")
        st.subheader("Expenses")
        if day_expenses.empty:
            st.info("No expenses recorded for this day.")
        else:
            st.dataframe(
                day_expenses,
                use_container_width=True,
                hide_index=True,
                column_config={"Amount": st.column_config.NumberColumn(format="₹%.2f")},
            )
            breakdown = day_expenses.groupby("Category", as_index=False)["Amount"].sum()
            st.subheader("Category-wise breakdown")
            st.dataframe(breakdown, use_container_width=True, hide_index=True)

    # ---------------------------- Manage data ----------------------------
    with tabs[5]:
        st.subheader("Delete an expense")
        expenses = read_df(
            """SELECT e.id, e.day, e.category, e.description, e.amount,
                      COALESCE(p.name, 'Not specified') AS paid_by
               FROM expenses e LEFT JOIN people p ON p.id = e.paid_by
               ORDER BY e.day, e.id"""
        )
        if expenses.empty:
            st.info("No expenses to manage.")
        else:
            expenses["label"] = expenses.apply(
                lambda r: f"#{int(r['id'])} | Day {int(r['day'])} | {r['category']} | "
                          f"{r['description'] or 'No description'} | {money(r['amount'])} | Paid by: {r['paid_by']}",
                axis=1,
            )
            chosen_expense = st.selectbox("Select expense to delete", expenses["label"].tolist())
            if st.button("🗑️ Delete selected expense", type="secondary"):
                expense_id = int(expenses.loc[expenses["label"] == chosen_expense, "id"].iloc[0])
                with get_connection() as conn:
                    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
                st.success("Expense deleted.")
                st.rerun()

        st.divider()
        st.subheader("Delete a deposit")
        deposits = read_df(
            """SELECT d.id, p.name, d.amount, d.deposit_date, d.note
               FROM deposits d JOIN people p ON p.id = d.person_id
               ORDER BY d.id DESC"""
        )
        if deposits.empty:
            st.info("No deposits to manage.")
        else:
            deposits["label"] = deposits.apply(
                lambda r: f"#{int(r['id'])} | {r['name']} | {money(r['amount'])} | {r['deposit_date'] or ''} | {r['note'] or ''}",
                axis=1,
            )
            chosen_deposit = st.selectbox("Select deposit to delete", deposits["label"].tolist())
            if st.button("🗑️ Delete selected deposit", type="secondary"):
                deposit_id = int(deposits.loc[deposits["label"] == chosen_deposit, "id"].iloc[0])
                with get_connection() as conn:
                    conn.execute("DELETE FROM deposits WHERE id = ?", (deposit_id,))
                st.success("Deposit deleted.")
                st.rerun()

        st.divider()
        st.subheader("Export all records")
        with get_connection() as conn:
            people_csv = pd.read_sql_query("SELECT * FROM people", conn).to_csv(index=False).encode("utf-8")
            participants_csv = pd.read_sql_query("SELECT * FROM day_participants", conn).to_csv(index=False).encode("utf-8")
            expenses_csv = pd.read_sql_query("SELECT * FROM expenses", conn).to_csv(index=False).encode("utf-8")
            deposits_csv = pd.read_sql_query("SELECT * FROM deposits", conn).to_csv(index=False).encode("utf-8")
        e1, e2, e3, e4 = st.columns(4)
        e1.download_button("People CSV", people_csv, "people.csv", "text/csv")
        e2.download_button("Participants CSV", participants_csv, "day_participants.csv", "text/csv")
        e3.download_button("Expenses CSV", expenses_csv, "expenses.csv", "text/csv")
        e4.download_button("Deposits CSV", deposits_csv, "deposits.csv", "text/csv")


if __name__ == "__main__":
    main()
