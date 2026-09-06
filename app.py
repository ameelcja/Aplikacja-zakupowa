import streamlit as st
import pandas as pd
import json
import re
import time
import plotly.graph_objects as go
from google import genai
from google.genai.errors import APIError

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Inteligentny Asystent Zakupowy & Kulinarny", layout="wide", initial_sidebar_state="expanded")

# Inicjalizacja stanu sesji
if "user_name" not in st.session_state:
    st.session_state.user_name = "Użytkowniku"

if "calculated_target_kcal" not in st.session_state:
    st.session_state.calculated_target_kcal = 2000

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

# ==========================================
# PASEK BOCZNY - NAWIGACJA
# ==========================================
st.sidebar.title(f"👋 Cześć, {st.session_state.user_name}!")

menu_choice = st.sidebar.radio(
    "Nawigacja:",
    [
        "👤 Profil, Zdrowie & Kalorie",
        "🍳 Planer posiłków i przepisów",
        "🏷️ Lista zakupów z promocjami",
        "📊 Lista na podstawie wag",
        "💬 Asystent AI"
    ]
)

st.sidebar.markdown("---")
st.sidebar.caption("🛒 **Inteligentny Asystent Zakupowy**\nPersonalizacja diety, wskaźniki BMI/CPM, Lidl/Auchan i matryca priorytetów.")

# ==========================================
# MODUŁ 0: PROFIL & KALKULATOR (BMI / CPM / MAKRO)
# ==========================================
if menu_choice == "👤 Profil, Zdrowie & Kalorie":
    st.title(f"Cześć, {st.session_state.user_name}! 👋")
    st.write("Skonfiguruj swój profil, aby aplikacja precyzyjnie dopasowywała zapotrzebowanie kaloryczne, jadłospisy i zakupy.")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        name_input = st.text_input("Jak masz na imię?", value=st.session_state.user_name if st.session_state.user_name != "Użytkowniku" else "")
        plec = st.radio("Płeć:", ["Kobieta", "Mężczyzna"], horizontal=True)
        wiek = st.number_input("Wiek (lata):", min_value=14, max_value=100, value=22, step=1)
        waga = st.number_input("Waga (kg):", min_value=35.0, max_value=200.0, value=60.0, step=0.5)
        wzrost = st.number_input("Wzrost (cm):", min_value=120, max_value=230, value=168, step=1)

    with col_p2:
        aktywnosc = st.selectbox(
            "Poziom aktywności fizycznej (tryb życia):",
            [
                "Siedzący (praca biurowa, mało ruchu) [PAL 1.2]",
                "Lekka aktywność (spacery, 1-2 lekkie treningi/tydz.) [PAL 1.4]",
                "Umiarkowana aktywność (regularne bieganie/treningi 3-4x/tydz.) [PAL 1.6]",
                "Duża aktywność (intensywne treningi 5-6x/tydz.) [PAL 1.8]"
            ]
        )
        cel = st.selectbox(
            "Twój cel sylwetkowy / zdrowotny:",
            [
                "Utrzymanie wagi (0 kcal)",
                "Redukcja umiarkowana (-300 kcal)",
                "Redukcja wyraźna (-500 kcal)",
                "Budowa masy mięśniowej (+300 kcal)"
            ]
        )

    # Obliczenia dietetyczne
    pal_factors = {
        "Siedzący (praca biurowa, mało ruchu) [PAL 1.2]": 1.2,
        "Lekka aktywność (spacery, 1-2 lekkie treningi/tydz.) [PAL 1.4]": 1.4,
        "Umiarkowana aktywność (regularne bieganie/treningi 3-4x/tydz.) [PAL 1.6]": 1.6,
        "Duża aktywność (intensywne treningi 5-6x/tydz.) [PAL 1.8]": 1.8
    }
    pal = pal_factors[aktywnosc]

    # BMR wzorem Mifflina-St Jeora
    if plec == "Kobieta":
        bmr = (10 * waga) + (6.25 * wzrost) - (5 * wiek) - 161
    else:
        bmr = (10 * waga) + (6.25 * wzrost) - (5 * wiek) + 5

    cpm = bmr * pal

    # Korekta o cel
    delta_kcal = 0
    if "Redukcja umiarkowana" in cel:
        delta_kcal = -300
    elif "Redukcja wyraźna" in cel:
        delta_kcal = -500
    elif "Budowa masy" in cel:
        delta_kcal = 300

    target_kcal_calc = int(round(cpm + delta_kcal))

    # BMI
    wzrost_m = wzrost / 100.0
    bmi = round(waga / (wzrost_m ** 2), 1)

    if bmi < 18.5:
        bmi_status = "Niedowaga"
        bmi_color = "#3498db"
    elif bmi < 25.0:
        bmi_status = "Waga w normie ✅"
        bmi_color = "#2ecc71"
    elif bmi < 30.0:
        bmi_status = "Nadwaga"
        bmi_color = "#f39c12"
    else:
        bmi_status = "Otyłość"
        bmi_color = "#e74c3c"

    woda_litry = round((waga * 35) / 1000, 1)

    st.markdown("---")
    st.subheader("📊 Twoje Wyliczone Wskaźniki Biometryczne")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Twoje BMI", f"{bmi}", bmi_status)
    m2.metric("Podstawowe BMR", f"{int(round(bmr))} kcal", "Zapotrzebowanie bazowe")
    m3.metric("Rekomendowane Kcal", f"{target_kcal_calc} kcal", f"Cel: {cel.split(' (')[0]}")
    m4.metric("Zalecana woda", f"{woda_litry} l / dzień", "Nawodnienie")

    # ==========================================
    # WYKRES SKALI BMI (PLOTLY)
    # ==========================================
    st.markdown("#### 📈 Wizualizacja Twojego BMI na skali")
    
    fig = go.Figure()

    # Paski stref BMI
    fig.add_trace(go.Bar(y=['BMI'], x=[18.5], name='Niedowaga (<18.5)', orientation='h', marker=dict(color='#5dade2')))
    fig.add_trace(go.Bar(y=['BMI'], x=[6.4], name='Norma (18.5 - 24.9)', orientation='h', marker=dict(color='#2ecc71')))
    fig.add_trace(go.Bar(y=['BMI'], x=[5.0], name='Nadwaga (25.0 - 29.9)', orientation='h', marker=dict(color='#f39c12')))
    fig.add_trace(go.Bar(y=['BMI'], x=[10.1], name='Otyłość (≥30.0)', orientation='h', marker=dict(color='#e74c3c')))

    # Linia wskazująca aktualne BMI
    fig.add_shape(
        type="line",
        x0=bmi, y0=-0.4, x1=bmi, y1=0.4,
        line=dict(color="black", width=4, dash="solid")
    )

    # Etykieta ze wskaźnikiem
    fig.add_annotation(
        x=bmi, y=0.5,
        text=f"Twoje BMI: <b>{bmi}</b> ({bmi_status})",
        showarrow=True,
        arrowhead=2,
        arrowsize=1.2,
        arrowwidth=2,
        arrowcolor="black",
        ax=0,
        ay=-35,
        font=dict(size=14, color=bmi_color)
    )

    fig.update_layout(
        barmode='stack',
        xaxis=dict(
            range=[10, 40],
            tickvals=[10, 18.5, 25, 30, 40],
            ticktext=['10', '18.5 (Niedowaga)', '25.0 (Norma)', '30.0 (Nadwaga)', '40 (Otyłość)'],
            title="Skala wskaźnika masy ciała (BMI)"
        ),
        yaxis=dict(showticklabels=False),
        height=220,
        margin=dict(l=20, r=20, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=-0.6, xanchor="center", x=0.5)
    )

    st.plotly_chart(fig, use_container_width=True)

    if st.button("💾 Zapisz profil i prześlij kalorie do Planera dań"):
        if name_input.strip():
            st.session_state.user_name = name_input.strip()
        st.session_state.calculated_target_kcal = target_kcal_calc
        st.success(f"Zapisano! Cel kaloryczny ({target_kcal_calc} kcal) został zsynchronizowany z Planerem posiłków.")
        st.rerun()

# ==========================================
# MODUŁ 1: PLANER POSIŁKÓW
# ==========================================
elif menu_choice == "🍳 Planer posiłków i przepisów":
    st.title(f"Cześć, {st.session_state.user_name}! 🍳")
    st.write("Dopasuj dzienny limit kalorii, posiłki, styl żywienia (w tym insulinooporność i dietę niskotłuszczową) oraz otrzymaj dokładne gramatury i wartości odżywcze.")

    col1, col2 = st.columns([1, 2])
    with col1:
        daily_calorie_target = st.number_input(
            "🔥 Dzienny limit kalorii (kcal):", 
            min_value=1000, 
            max_value=4500, 
            value=int(st.session_state.calculated_target_kcal), 
            step=50
        )
        days_count = st.slider("Liczba dni:", min_value=1, max_value=7, value=2)
        diet_type = st.selectbox(
            "Styl żywienia / Dieta:",
            [
                "Dla insulinoopornych (Niski IG)",
                "Niskotłuszczowa (Low-Fat)",
                "Wysokobiałkowa (High-Protein)",
                "Zrównoważona / Standardowa",
                "Wegetariańska",
                "Ekonomiczna / Budżetowa"
            ]
        )
        
        selected_meals = st.multiselect(
            "Wybierz posiłki do zaplanowania na każdy dzień:",
            ["Śniadanie", "Drugie śniadanie", "Obiad", "Podwieczorek", "Kolacja", "Przekąska"],
            default=["Śniadanie", "Obiad", "Kolacja"]
        )

    with col2:
        preferences = st.text_area(
            "Preferencje kulinarne, wykluczenia lub składniki:",
            placeholder="np. wytrawne śniadania, dużo warzyw o niskim IG, pierś z kurczaka, bez laktozy",
            height=140
        )

    def generate_meal_plan_advanced(target_kcal, days, diet, meals, prefs):
        client = genai.Client(api_key=API_KEY)
        meals_str = ", ".join(meals)
        prompt = f"""
        Jesteś dyplomowanym dietetykiem klinicznym w Polsce.
        Przygotuj precyzyjny jadłospis na {days} dni dla użytkownika o imieniu {st.session_state.user_name}:
        - DZIENNY CEL KALORII: dokładnie około {target_kcal} kcal na każdy dzień (+/- 50 kcal).
        - Dieta: {diet} (Dla insulinooporności: niski IG/ładunek, zdrowe źródła węglowodanów i tłuszczu; dla niskotłuszczowej: lekka, chudy nabiał, ograniczenie tłuszczów).
        - Wybrane posiłki na dzień: {meals_str}
        - Uwagi: {prefs if prefs else "brak"}

        Dla KAŻDEGO posiłku podaj:
        1. "typ": np. 'Śniadanie', 'Obiad' itp.
        2. "nazwa": nazwa potrawy
        3. "skladniki_gramatura": lista składników Z ZAWSZE PODANĄ DOKŁADNĄ WAGĄ W GRAMACH LUB SZTUKACH (np. "180 g piersi z kurczaka", "70 g ryżu basmati", "150 g brokułu", "10 g oliwy").
        4. "wartosci_odzywcze": {{"kcal": 450, "b": 35, "t": 10, "w": 55}}
        5. "przepis": krótki, 2-3 zdaniowy sposób przygotowania.

        Na koniec stwórz zsumowaną listę artykułów z podaniem łącznej wagi/opakowań do kupienia w sklepie.

        Zwróć WYŁĄCZNIE czysty JSON w postaci obiektu:
        {{
          "dni": [
            {{
              "dzien": 1,
              "suma_kcal_dnia": {target_kcal},
              "posilki": [
                {{
                  "typ": "Śniadanie",
                  "nazwa": "Jajecznica ze szczypiorkiem i żytnim pieczywem",
                  "skladniki_gramatura": ["3 szt. jajka (150 g)", "5 g masła", "20 g szczypiorku", "70 g chleba żytniego"],
                  "wartosci_odzywcze": {{"kcal": 380, "b": 24, "t": 18, "w": 30}},
                  "przepis": "Rozgrzej patelnię z masłem. Wbij jajka, smaż na małym ogniu i posyp szczypiorkiem."
                }}
              ]
            }}
          ],
          "lista_zakupow": ["jajka 6 szt.", "chleb żytni 1 bochenek", "masło 1 op.", "szczypiorek 1 pęczek"]
        }}
        """
        raw = generate_with_fallback(client, prompt)
        return json.loads(clean_json_string(raw))

    if st.button("✨ Generuj jadłospis z limitem kalorii i makro"):
        if not selected_meals:
            st.warning("Zaznacz przynajmniej jeden posiłek.")
        else:
            with st.spinner(f"AI bilansuje posiłki pod cel {daily_calorie_target} kcal/dzień..."):
                try:
                    plan = generate_meal_plan_advanced(daily_calorie_target, days_count, diet_type, selected_meals, preferences)
                    st.session_state.meal_plan_data = plan
                    st.session_state.shared_shopping_list = ", ".join(plan.get("lista_zakupow", []))
                    
                    context_rows = []
                    for d in plan.get("dni", []):
                        s_kcal = d.get('suma_kcal_dnia', daily_calorie_target)
                        context_rows.append(f"Dzień {d['dzien']} (Łącznie: ~{s_kcal} kcal):")
                        for p in d.get("posilki", []):
                            macro = p.get("wartosci_odzywcze", {})
                            context_rows.append(f"  - {p['typ']}: {p['nazwa']} ({macro.get('kcal', 0)} kcal | B:{macro.get('b', 0)}g T:{macro.get('t', 0)}g W:{macro.get('w', 0)}g)")
                    st.session_state.last_context = f"PROFIL ({st.session_state.user_name}, Dieta: {diet_type}, Cel: {daily_calorie_target} kcal):\n" + "\n".join(context_rows) + "\nZAKUPY: " + st.session_state.shared_shopping_list
                except Exception as e:
                    st.error(f"Błąd generowania planu: {e}")

    if st.session_state.meal_plan_data:
        plan = st.session_state.meal_plan_data
        st.markdown("---")
        st.subheader("📋 Zaplanowane Posiłki, Gramatury i Wartości Odżywcze")
        
        for d in plan.get("dni", []):
            posilki = d.get("posilki", [])
            suma_kcal_dnia = sum(p.get("wartosci_odzywcze", {}).get("kcal", 0) for p in posilki)
            suma_b_dnia = sum(p.get("wartosci_odzywcze", {}).get("b", 0) for p in posilki)
            suma_t_dnia = sum(p.get("wartosci_odzywcze", {}).get("t", 0) for p in posilki)
            suma_w_dnia = sum(p.get("wartosci_odzywcze", {}).get("w", 0) for p in posilki)

            st.markdown(f"### 📅 Dzień {d.get('dzien', 1)} — Bilans: `{suma_kcal_dnia} kcal` (B: {suma_b_dnia}g | T: {suma_t_dnia}g | W: {suma_w_dnia}g)")
            
            cols = st.columns(len(posilki)) if posilki else [st.container()]
            for idx, p in enumerate(posilki):
                with cols[idx]:
                    st.markdown(f"**{p.get('typ', 'Posiłek')}**")
                    st.write(f"*{p.get('nazwa', '')}*")
                    
                    macro = p.get("wartosci_odzywcze", {})
                    st.caption(f"🔥 **{macro.get('kcal', 0)} kcal** | B: {macro.get('b', 0)}g | T: {macro.get('t', 0)}g | W: {macro.get('w', 0)}g")
                    
                    with st.expander("⚖️ Gramatura składników", expanded=True):
                        for sk in p.get("skladniki_gramatura", []):
                            st.write(f"- {sk}")
                    
                    with st.expander("👨‍🍳 Przepis"):
                        st.write(p.get("przepis", ""))

        st.markdown("---")
        st.subheader("🛒 Precyzyjna Zbiorcza Lista Zakupów")
        st.success(st.session_state.shared_shopping_list)
        st.info("💡 Składniki wraz z gramaturami zostały zapisane! W zakładce **🏷️ Lista zakupów z promocjami** możesz od razu rozdzielić te produkty na Lidl i Auchan.")

# ==========================================
# MODUŁ 2: LISTA PROMOCJI (LIDL & AUCHAN)
# ==========================================
elif menu_choice == "🏷️ Lista zakupów z promocjami":
    st.title(f"Cześć, {st.session_state.user_name}! 🏷️")
    st.write("AI porównuje oferty w sieciach Lidl oraz Auchan, wyznacza opłacalność i grupuje listę na sklepy.")

    budget_promotions = st.number_input("Twój budżet łączny (zł):", min_value=0.0, value=250.0, step=25.0, key="budget_promo")
    
    default_text = st.session_state.shared_shopping_list if st.session_state.shared_shopping_list else "chleb żytni 100% 1 szt., pierś z kurczaka 500 g, oliwa z oliwek 500 ml, jaja z wolnego wybiegu 10 szt., pomidory malinowe 500 g, jogurt naturalny skyr 2 szt."
    
    raw_promotions = st.text_area(
        "Artykuły do kupienia (przeniesione z planera z gramaturami):",
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
        1. "name": nazwa produktu (z uwzględnieniem gramatury/opakowania)
        2. "sklep": 'Lidl' lub 'Auchan'
        3. "cena_pln": szacunkowa cena w PLN
        4. "ocena_koszt": 1-5 (5 = tani/przystępny, 1 = drogi)
        5. "ocena_potrzeba": 1-5 (5 = pierwsza potrzeba/zdrowie, 1 = zbędny)
        6. "ocena_okazja": 1-5 (5 = świetna cena/marka własna)
        7. "uwagi": krótkie uzasadnienie wyboru

        Zwróć WYŁĄCZNIE czysty JSON w postaci tablicy:
        [
          {{"name": "Pierś z kurczaka 500 g", "sklep": "Lidl", "cena_pln": 12.99, "ocena_koszt": 4.0, "ocena_potrzeba": 5.0, "ocena_okazja": 4.5, "uwagi": "Częste promocje na tacki XXL w Lidlu"}}
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

# ==========================================
# MODUŁ 3: LISTA NA PODSTAWIE WAG
# ==========================================
elif menu_choice == "📊 Lista na podstawie wag":
    st.title(f"Cześć, {st.session_state.user_name}! 📊")
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
    
    default_mat_text = st.session_state.shared_shopping_list if st.session_state.shared_shopping_list else "chleb żytni, pierś z kurczaka, oliwa z oliwek, jajka, rower miejski, kurtka"
    
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
        3. "koszt_pkt": ocena 1-5 (5 = tani, 1 = drogi)
        4. "potrzeba_pkt": ocena 1-5 (5 = konieczność życiowa/zdrowotna, 1 = luksus)
        5. "dostepnosc_pkt": ocena 1-5 (5 = rzadki/trudnodostępny, 1 = powszechny od ręki)

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

# ==========================================
# MODUŁ 4: ASYSTENT AI (CZAT NA ŻYWO)
# ==========================================
elif menu_choice == "💬 Asystent AI":
    st.title(f"Cześć, {st.session_state.user_name}! 💬")
    st.write("Dyskutuj na żywo o zaplanowanych posiłkach, przepisach, zamiennikach składników, stylu życia, kaloriach i promocjach.")

    if st.session_state.last_context:
        with st.expander("📌 Aktywny kontekst z Twoich wcześniejszych analiz"):
            st.text(st.session_state.last_context)

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_msg = st.chat_input("Napisz pytanie, np.: Jak dobić 300 kcal w kolacji? Jak zamienić ten makaron?")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

        client = genai.Client(api_key=API_KEY)
        chat_prompt = f"""
        Jesteś dyplomowanym doradcą żywieniowym i zakupowym w Polsce.
        Rozmawiasz z użytkownikiem o imieniu {st.session_state.user_name}.
        Znasz diety kliniczne (insulinooporność, niskotłuszczowa), bilansowanie kalorii, gramatury i makroskładniki oraz doradzasz tanie zakupy w Lidlu i Auchan.
        Zwracaj się bezpośrednio i naturalnie po imieniu.

        Kontekst ostatnich analiz użytkownika:
        {st.session_state.last_context if st.session_state.last_context else "Brak wcześniejszych danych."}

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
