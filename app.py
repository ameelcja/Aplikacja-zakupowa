import streamlit as st
import pandas as pd
import json
import re
import time
from google import genai
from google.genai.errors import APIError

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Inteligentny Asystent Zakupowy & Kulinarny", layout="wide", initial_sidebar_state="expanded")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "promotions_df" not in st.session_state:
    st.session_state.promotions_df = None

if "matrix_df" not in st.session_state:
    st.session_state.matrix_df = None

if "meal_plan_data" not in st.session_state:
    st.session_state.meal_plan_data = None

if "shared_shopping_list" not in st.session_state:
    st.session_state.shared_shopping_list = ""

if "last_context" not in st.session_state:
    st.session_state.last_context = ""

def clean_json_string(text):
    text = text.strip()
    match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
    if match:
        return match.group(1)
    b = chr(96)
    pattern = rf'{b}{{3}}[a-zA-Z]*|{b}{{3}}'
    return re.sub(pattern, '', text).strip()

def get_supported_models(client):
    active_models = []
    try:
        for m in client.models.list():
            name = getattr(m, 'name', '')
            if 'flash' in name.lower():
                active_models.append(name.replace('models/', ''))
    except Exception:
        pass
    
    preferred_order = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
    sorted_models = [m for m in preferred_order if m in active_models]
    for m in active_models:
        if m not in sorted_models:
            sorted_models.append(m)
            
    return sorted_models if sorted_models else preferred_order

def generate_with_fallback(client, prompt):
    candidate_models = get_supported_models(client)
    last_err = None

    for model_name in candidate_models:
        for _ in range(2):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return resp.text
            except APIError as e:
                last_err = e
                if e.code in [503, 429]:
                    time.sleep(2)
                    continue
                break
            except Exception as e:
                last_err = e
                if "503" in str(e) or "429" in str(e):
                    time.sleep(2)
                    continue
                break

    raise RuntimeError(f"Blad polaczenia z modelem AI: {last_err}")

st.sidebar.title("🧭 Menu Aplikacji")

menu_choice = st.sidebar.radio(
    "Wybierz moduł:",
    [
        "🍳 Planer posiłków i przepisów",
        "🏷️ Lista zakupów z promocjami",
        "📊 Lista na podstawie wag",
        "💬 Asystent AI"
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption("🛒 **Inteligentny Asystent Zakupowy**\nPlanowanie dań, oferty Lidl/Auchan i matryca wagowa.")

if menu_choice == "🍳 Planer posiłków i przepisów":
    st.title("🍳 Planer Posiłków & Generator Listy Zakupów")
    st.write("AI zaplanuje dla Ciebie śniadania, obiady i kolacje, poda zwięzłe przepisy i wygeneruje kompletną listę zakupów.")

    col1, col2 = st.columns([1, 2])
    with col1:
        days_count = st.slider("Liczba dni:", min_value=1, max_value=7, value=3)
        diet_type = st.selectbox(
            "Styl żywienia:",
            ["Zrównoważona / Standardowa", "Wysokobiałkowa (High-Protein)", "Wegetariańska", "Szybka i prosta (do 20 min)", "Ekonomiczna / Budżetowa"]
        )
    with col2:
        preferences = st.text_input(
            "Preferencje kulinarne, wykluczenia lub składniki:",
            placeholder="np. wytrawne śniadania, dużo warzyw, bez owoców morza, lubię kurczaka"
        )

    def generate_meal_plan(days, diet, prefs):
        client = genai.Client(api_key=API_KEY)
        prompt = f"""
        Jesteś dietetykiem i kucharzem w Polsce.
        Przygotuj zrównoważony jadłospis na {days} dni:
        - Styl: {diet}
        - Preferencje: {prefs if prefs else "brak"}

        Dla każdego dnia uwzględnij: Śniadanie, Obiad, Kolacja.
        Dla każdego posiłku: nazwa dania, składniki, krótki przepis (2-3 zdania).
        Na koniec podaj zbiorczą listę zakupów.

        Zwróć WYŁĄCZNIE czysty JSON w postaci obiektu:
        {{
          "dni": [
            {{
              "dzien": 1,
              "sniadanie": {{"nazwa": "Jajecznica ze szczypiorkiem", "skladniki": ["jajka", "szczypiorek", "masło"], "przepis": "Podsmaż masło, wbij jajka i posyp szczypiorkiem."}},
              "obiad": {{"nazwa": "Pierś z kurczaka z warzywami", "skladniki": ["pierś z kurczaka", "cukinia", "oliwa"], "przepis": "Upiecz przyprawione mięso i warzywa w 180 stopniach."}},
              "kolacja": {{"nazwa": "Twarożek z rzodkiewką", "skladniki": ["twaróg", "jogurt naturalny", "rzodkiewka"], "przepis": "Wymieszaj twaróg z jogurtem i posiekaną rzodkiewką."}}
            }}
          ],
          "lista_zakupow": ["jajka", "szczypiorek", "masło", "pierś z kurczaka", "cukinia", "oliwa", "twaróg", "jogurt naturalny", "rzodkiewka"]
        }}
        """
        raw = generate_with_fallback(client, prompt)
        return json.loads(clean_json_string(raw))

    if st.button("✨ Zaplanuj posiłki i stwórz listę zakupów"):
        with st.spinner("AI komponuje jadłospis, przepisy i listę zakupów..."):
            try:
                plan = generate_meal_plan(days_count, diet_type, preferences)
                st.session_state.meal_plan_data = plan
                st.session_state.shared_shopping_list = ", ".join(plan.get("lista_zakupow", []))
                
                summary_plan = []
                for d in plan.get("dni", []):
                    summary_plan.append(f"Dzień {d['dzien']}: Śniadanie: {d['sniadanie']['nazwa']}, Obiad: {d['obiad']['nazwa']}, Kolacja: {d['kolacja']['nazwa']}")
                st.session_state.last_context = "JADŁOSPIS:\n" + "\n".join(summary_plan) + "\nSKŁADNIKI: " + st.session_state.shared_shopping_list
            except Exception as e:
                st.error(f"Błąd generowania jadłospisu: {e}")

    if st.session_state.meal_plan_data:
        plan = st.session_state.meal_plan_data
        st.markdown("---")
        st.subheader("📋 Zaplanowany Jadłospis & Przepisy")
        
        for d in plan.get("dni", []):
            with st.expander(f"📅 Dzień {d.get('dzien', 1)}", expanded=True):
                col_s, col_o, col_k = st.columns(3)
                
                with col_s:
                    st.markdown("#### 🍳 Śniadanie")
                    st.write(f"**{d['sniadanie']['nazwa']}**")
                    st.caption(f"Składniki: {', '.join(d['sniadanie']['skladniki'])}")
                    st.info(d['sniadanie']['przepis'])

                with col_o:
                    st.markdown("#### 🍲 Obiad")
                    st.write(f"**{d['obiad']['nazwa']}**")
                    st.caption(f"Składniki: {', '.join(d['obiad']['skladniki'])}")
                    st.info(d['obiad']['przepis'])

                with col_k:
                    st.markdown("#### 🥗 Kolacja")
                    st.write(f"**{d['kolacja']['nazwa']}**")
                    st.caption(f"Składniki: {', '.join(d['kolacja']['skladniki'])}")
                    st.info(d['kolacja']['przepis'])

        st.markdown("---")
        st.subheader("🛒 Wygenerowana Zbiorcza Lista Zakupów")
        st.success(st.session_state.shared_shopping_list)
        st.info("💡 Składniki zapisane. Przejdź do zakładki z promocjami lub matrycy wagowej, by zaplanować wydatki.")

elif menu_choice == "🏷️ Lista zakupów z promocjami":
    st.title("🏷️ Lista zakupów z promocjami (Lidl vs Auchan)")
    st.write("AI porównuje oferty w sieciach Lidl oraz Auchan, wyznacza opłacalność i grupuje listę na sklepy.")

    budget_promotions = st.number_input("Twój budżet łączny (zł):", min_value=0.0, value=250.0, step=25.0, key="budget_promo")
    
    default_text = st.session_state.shared_shopping_list if st.session_state.shared_shopping_list else "chleb żytni na zakwasie, mleko owsiane, dojrzałe awokado, kawa ziarnista, świeża bazylia, pomidory malinowe, ser halloumi, pasta do zębów, oliwa z oliwek extra virgin, cytryny, hummus klasyczny, płatki owsiane górskie, jajka z wolnego wybiegu"
    
    raw_promotions = st.text_area(
        "Wpisz artykuły do kupienia (lub użyj listy z planera dań):",
        value=default_text,
        height=110,
        key="input_promo"
    )

    def analyze_promotions(items_list):
        client = genai.Client(api_key=API_KEY)
        prompt = f"""
        Przeanalizuj poniższe artykuły pod kątem opłacalności w sieciach LIDL Polska oraz AUCHAN Polska:
        {', '.join(items_list)}

        Dla każdego produktu wskaż:
        1. "name": nazwa produktu
        2. "sklep": 'Lidl' lub 'Auchan'
        3. "cena_pln": szacowana cena w PLN
        4. "ocena_koszt": 1-5 (5 = bardzo tani, 1 = drogi)
        5. "ocena_potrzeba": 1-5 (5 = pierwsza potrzeba, 1 = zbędny luksus)
        6. "ocena_okazja": 1-5 (5 = bardzo opłacalna oferta/marka własna)
        7. "uwagi": krótkie uzasadnienie

        Zwróć WYŁĄCZNIE czysty JSON w postaci tablicy:
        [
          {{"name": "Masło", "sklep": "Lidl", "cena_pln": 6.29, "ocena_koszt": 4.0, "ocena_potrzeba": 5.0, "ocena_okazja": 4.0, "uwagi": "Tania marka własna Pilos"}}
        ]
        """
        raw = generate_with_fallback(client, prompt)
        return json.loads(clean_json_string(raw))

    if st.button("🔍 Optymalizuj koszyki i przelicz promocje"):
        if not raw_promotions.strip():
            st.warning("Wpisz przynajmniej jeden produkt.")
        else:
            items = [x.strip() for x in raw_promotions.replace("\n", ",").split(",") if x.strip()]
            with st.spinner("AI analizuje oferty Lidl i Auchan..."):
                try:
                    data = analyze_promotions(items)
                    parsed = []
                    for entry in data:
                        cena = float(entry.get("cena_pln", 10.0))
                        k = float(entry.get("ocena_koszt", 3.0))
                        p = float(entry.get("ocena_potrzeba", 3.0))
                        o = float(entry.get("ocena_okazja", 2.0))
                        prio = round((k * 0.5) + (p * 0.4) + (o * 0.3), 2)
                        parsed.append({
                            "Produkt": entry.get("name", "").capitalize(),
                            "Rekomendowany sklep": entry.get("sklep", "Lidl"),
                            "koszt": k,
                            "potrzeba": p,
                            "dostępność/okazja": o,
                            "Priorytet": prio,
                            "Cena (zł)": cena,
                            "Wskazówka": entry.get("uwagi", "")
                        })
                    
                    df = pd.DataFrame(parsed).sort_values(by="Priorytet", ascending=False).reset_index(drop=True)
                    
                    allocated = 0.0
                    status = []
                    for _, row in df.iterrows():
                        if allocated + row["Cena (zł)"] <= budget_promotions:
                            allocated += row["Cena (zł)"]
                            status.append("✅ Kup teraz")
                        else:
                            status.append("⏳ Odłóż")
                    df["Decyzja"] = status

                    st.session_state.promotions_df = df
                    st.session_state.promotions_allocated = allocated
                    st.session_state.promotions_budget = budget_promotions
                    
                    lines = [f"{r['Produkt']} -> {r['Rekomendowany sklep']} (~{r['Cena (zł)']} zł, {r['Decyzja']}, {r['Wskazówka']})" for _, r in df.iterrows()]
                    st.session_state.last_context = "LISTA PROMOCJI (LIDL / AUCHAN):\n" + "\n".join(lines)
                except Exception as e:
                    st.error(f"Błąd analizy: {e}")

    if st.session_state.promotions_df is not None:
        df = st.session_state.promotions_df
        st.subheader("📋 Matryca priorytetów i rekomendacje")
        st.dataframe(df, use_container_width=True)

        col1, col2 = st.columns(2)
        col1.metric("Wykorzystany budżet", f"{st.session_state.promotions_allocated:.2f} zł")
        col2.metric("Pozostało środków", f"{st.session_state.promotions_budget - st.session_state.promotions_allocated:.2f} zł")

        st.markdown("---")
        st.subheader("🛒 Gotowe listy zakupów z podziałem na sklepy")
        col_l, col_a = st.columns(2)

        df_kupione = df[df["Decyzja"] == "✅ Kup teraz"]

        with col_l:
            st.markdown("### 🟡🔵 Lidl")
            lidl_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Lidl"]
            if not lidl_items.empty:
                for _, r in lidl_items.iterrows():
                    st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka']})*")
                st.caption(f"Suma w Lidlu: **{lidl_items['Cena (zł)'].sum():.2f} zł**")
            else:
                st.info("Brak zakupów w Lidlu.")

        with col_a:
            st.markdown("### 🔴🟢 Auchan")
            auchan_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Auchan"]
            if not auchan_items.empty:
                for _, r in auchan_items.iterrows():
                    st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka']})*")
                st.caption(f"Suma w Auchan: **{auchan_items['Cena (zł)'].sum():.2f} zł**")
            else:
                st.info("Brak zakupów w Auchan.")

elif menu_choice == "📊 Lista na podstawie wag":
    st.title("📊 Lista zakupów na podstawie wag (Matryca Priorytetów)")
    st.write("Wielokryterialna matryca priorytetów obliczana wg wag: **koszt (0,5)**, **potrzeba (0,4)**, **dostępność (0,3)**.")

    st.markdown("""
    | Nazwa produktu | koszt | potrzeba | dostępność | Priorytet |
    | :--- | :---: | :---: | :---: | :---: |
    | **skala** | **0,5** | **0,4** | **0,3** | $\sum(\text{wartość} \times \text{waga})$ |
    """)

    col_w1, col_w2, col_w3 = st.columns(3)
    w_k = col_w1.number_input("Waga kosztu:", value=0.5, step=0.05, key="w_k")
    w_p = col_w2.number_input("Waga potrzeby:", value=0.4, step=0.05, key="w_p")
    w_d = col_w3.number_input("Waga dostępności:", value=0.3, step=0.05, key="w_d")

    budget_matrix = st.number_input("Dostępny budżet (zł):", min_value=0.0, value=500.0, step=50.0, key="budget_mat")
    
    default_mat_text = st.session_state.shared_shopping_list if st.session_state.shared_shopping_list else "telewizor, chleb, rower miejski, leki przeciwbólowe, kurtka zimowa, karma dla psa, fotel biurowy, jajka"
    
    raw_matrix = st.text_area(
        "Wpisz produkty do oceny:",
        value=default_mat_text,
        height=100,
        key="input_mat"
    )

    def analyze_matrix(items_list):
        client = genai.Client(api_key=API_KEY)
        prompt = f"""
        Dokonaj analitycznej oceny poniższych produktów na rynku polskim:
        {', '.join(items_list)}

        Dla każdego produktu oszacuj:
        1. "name": nazwa produktu
        2. "cena_pln": realna szacunkowa cena w PLN
        3. "koszt_pkt": ocena 1-5 (5 = tani/drobny wydatek, 1 = drogi zakup)
        4. "potrzeba_pkt": ocena 1-5 (5 = konieczność życiowa/zdrowotna, 1 = luksus)
        5. "dostepnosc_pkt": ocena 1-5 (5 = rzadki/końcówka zapasów, 1 = powszechnie dostępny od ręki)

        Zwróć WYŁĄCZNIE poprawny format JSON w postaci tablicy:
        [
          {{"name": "Produkt", "cena_pln": 50.0, "koszt_pkt": 4.0, "potrzeba_pkt": 5.0, "dostepnosc_pkt": 2.0}}
        ]
        """
        raw = generate_with_fallback(client, prompt)
        return json.loads(clean_json_string(raw))

    if st.button("🧮 Wylicz priorytety z matrycy"):
        if not raw_matrix.strip():
            st.warning("Wpisz przynajmniej jeden produkt.")
        else:
            items = [x.strip() for x in raw_matrix.replace("\n", ",").split(",") if x.strip()]
            with st.spinner("AI ocenia parametry produktów i wylicza sumę ważoną..."):
                try:
                    data = analyze_matrix(items)
                    parsed = []
                    for entry in data:
                        cena = float(entry.get("cena_pln", 50.0))
                        k = float(entry.get("koszt_pkt", 3.0))
                        p = float(entry.get("potrzeba_pkt", 3.0))
                        d = float(entry.get("dostepnosc_pkt", 2.0))
                        prio = round((k * w_k) + (p * w_p) + (d * w_d), 2)
                        
                        parsed.append({
                            "Nazwa produktu": entry.get("name", "").capitalize(),
                            "koszt": k,
                            "potrzeba": p,
                            "dostępność": d,
                            "Priorytet": prio,
                            "Szacowana cena (zł)": cena
                        })

                    df = pd.DataFrame(parsed).sort_values(by="Priorytet", ascending=False).reset_index(drop=True)

                    allocated = 0.0
                    status = []
                    for _, row in df.iterrows():
                        if allocated + row["Szacowana cena (zł)"] <= budget_matrix:
                            allocated += row["Szacowana cena (zł)"]
                            status.append("✅ Kup teraz")
                        else:
                            status.append("⏳ Odłóż")
                    df["Decyzja"] = status

                    st.session_state.matrix_df = df
                    st.session_state.matrix_allocated = allocated
                    st.session_state.matrix_budget = budget_matrix

                    lines = [f"{r['Nazwa produktu']} (koszt:{r['koszt']}, potrzeba:{r['potrzeba']}, dostepnosc:{r['dostępność']} -> Prio:{r['Priorytet']}, Decyzja:{r['Decyzja']})" for _, r in df.iterrows()]
                    st.session_state.last_context = "MATRYCA WAG:\n" + "\n".join(lines)
                except Exception as e:
                    st.error(f"Błąd analizy: {e}")

    if st.session_state.matrix_df is not None:
        df = st.session_state.matrix_df
        st.subheader("📋 Wyniki matrycy wagowej")
        st.dataframe(df, use_container_width=True)

        c1, c2 = st.columns(2)
        c1.metric("Wykorzystana kwota", f"{st.session_state.matrix_allocated:.2f} zł")
        c2.metric("Pozostało w budżecie", f"{st.session_state.matrix_budget - st.session_state.matrix_allocated:.2f} zł")

elif menu_choice == "💬 Asystent AI":
    st.title("💬 Asystent AI - Kulinarny & Zakupowy Doradca")
    st.write("Dyskutuj na żywo o zaplanowanych posiłkach, przepisach, zamiennikach składników i promocjach.")

    if st.session_state.last_context:
        with st.expander("📌 Aktywny kontekst z Twoich wcześniejszych analiz"):
            st.text(st.session_state.last_context)

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("Napisz pytanie, np.: Jak przyspieszyć przygotowanie tego obiadu? Czym zastąpić składnik?")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

        client = genai.Client(api_key=API_KEY)
        chat_prompt = f"""
        Jesteś doradcą zakupowo-kulinarnym w Polsce.
        Pomagasz w planowaniu dań, przepisach, zamiennikach i optymalizacji zakupów pod kątem sklepów Lidl i Auchan.
        Odpowiadaj zwięźle, po polsku.

        Kontekst ostatnich działań użytkownika:
        {st.session_state.last_context if st.session_state.last_context else "Brak wcześniejszych analiz."}

        Pytanie: {user_msg}
        """

        with st.chat_message("assistant"):
            with st.spinner("Odpowiadam..."):
                try:
                    reply = generate_with_fallback(client, chat_prompt)
                    st.markdown(reply)
                    st.session_state.chat_history.append({"role": "assistant", "content": reply})
                except Exception as e:
                    st.error(f"Błąd odpowiedzi asystenta: {e}")
