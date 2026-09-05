import streamlit as st
import pandas as pd
import json
import re
import time
from google import genai
from google.genai.errors import APIError

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Inteligentne Zakupy: Lidl vs Auchan", layout="wide")

st.title("🛒 Asystent Promocji: Lidl & Auchan")
st.write("Wpisz produkty, a AI przeanalizuje typowe poziomy cen i specyfikę ofert Lidla oraz Auchan, przeliczy priorytety i rozdzieli listę na sklepy.")

# Wagi kryteriów
st.sidebar.header("⚖️ Skala wagowa kryteriów")
waga_koszt = st.sidebar.number_input("Waga: Koszt / Przystępność", value=0.5, step=0.1)
waga_potrzeba = st.sidebar.number_input("Waga: Potrzeba", value=0.4, step=0.1)
waga_dostepnosc = st.sidebar.number_input("Waga: Okazja / Dostępność", value=0.3, step=0.1)

budget = st.number_input("Dostępny budżet łącznie (zł):", min_value=0.0, value=250.0, step=25.0)

raw_input = st.text_area(
    "Twoja lista zakupów:", 
    placeholder="np. chleb żytni, mleko owsiane, awokado, kawa ziarnista, bazylia, pomidory malinowe",
    height=100
)

def analyze_promotions_and_assign_shops(items_list):
    client = genai.Client(api_key=API_KEY)

    prompt = f"""
    Jesteś polskim ekspertem ds. optymalizacji zakupów spożywczych i rynkowych.
    Przeanalizuj poniższe artykuły pod kątem realnych cen, marek własnych i opłacalności w sieciach LIDL Polska oraz AUCHAN Polska:
    {', '.join(items_list)}

    Dla każdego artykułu:
    1. "name": nazwa produktu
    2. "sklep": wybierz 'Lidl' lub 'Auchan' (dobierz sklep, w którym ten produkt ma lepszy stosunek ceny do jakości, tańsze marki własne lub ogólnie korzystniejsze ceny rynkowe).
    3. "cena_pln": szacunkowa realna cena rynkowa w PLN (liczba, np. 5.99).
    4. "ocena_koszt": w skali 1-5 (5 = artykuł tani / oszczędny wydatek, 1 = drogi artykuł).
    5. "ocena_potrzeba": w skali 1-5 (5 = artykuł pierwszej potrzeby, zdrowie, żywność codzienna, 1 = zachcianka / luksus).
    6. "ocena_okazja": w skali 1-5 pod kątem atrakcyjności oferty (5 = wyjątkowo opłacalny wybór w tym sklepie, 1 = standardowa cena).
    7. "uwagi": krótkie uzasadnienie wyboru (np. 'Lepsze ceny marek własnych w Lidlu', 'Większy asortyment i niższa cena w Auchan').

    Zwróć WYŁĄCZNIE czysty format JSON w postaci tablicy obiektów:
    [
      {{"name": "Masło", "sklep": "Lidl", "cena_pln": 6.29, "ocena_koszt": 4.0, "ocena_potrzeba": 5.0, "ocena_okazja": 4.0, "uwagi": "Dobre masło marki Pilos"}}
    ]
    """

    # Lista modeli w kolejności priorytetu
    candidate_models = [
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite"
    ]

    last_error = None

    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                text = response.text.strip()
                match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                return json.loads(text.replace("```json", "").replace("```", "").strip())
            except APIError as e:
                last_error = e
                if e.code == 503:
                    time.sleep(2)
                    continue
                break
            except Exception as e:
                last_error = e
                if "503" in str(e):
                    time.sleep(2)
                    continue
                break

    raise RuntimeError(f"Wszystkie modele są chwilowo przeciążone. Spróbuj za chwilę. Ostatni błąd: {last_error}")

if st.button("🔍 Optymalizuj koszyki i przelicz priorytety"):
    if not raw_input.strip():
        st.warning("Wpisz przynajmniej jeden produkt.")
    else:
        items_raw = [x.strip() for x in raw_input.replace("\n", ",").split(",") if x.strip()]
        
        with st.spinner("AI analizuje opłacalność w Lidlu i Auchan oraz wyznacza priorytety..."):
            try:
                data = analyze_promotions_and_assign_shops(items_raw)
                parsed = []

                for entry in data:
                    cena = float(entry.get("cena_pln", 10.0))
                    pkt_k = float(entry.get("ocena_koszt", 3.0))
                    pkt_p = float(entry.get("ocena_potrzeba", 3.0))
                    pkt_o = float(entry.get("ocena_okazja", 2.0))

                    priorytet = round(
                        (pkt_k * waga_koszt) + (pkt_p * waga_potrzeba) + (pkt_o * waga_dostepnosc), 
                        2
                    )

                    parsed.append({
                        "Produkt": entry.get("name", "").capitalize(),
                        "Rekomendowany sklep": entry.get("sklep", "Lidl"),
                        "Cena (zł)": cena,
                        "koszt": pkt_k,
                        "potrzeba": pkt_p,
                        "dostępność/okazja": pkt_o,
                        "Priorytet": priorytet,
                        "Wskazówka": entry.get("uwagi", "")
                    })

                df = pd.DataFrame(parsed)
                df = df.sort_values(by="Priorytet", ascending=False).reset_index(drop=True)

                allocated = 0.0
                status = []
                for _, row in df.iterrows():
                    if allocated + row["Cena (zł)"] <= budget:
                        allocated += row["Cena (zł)"]
                        status.append("✅ Kup teraz")
                    else:
                        status.append("⏳ Odłóż")
                df["Decyzja"] = status

                st.subheader("📋 Matryca priorytetów i rekomendacje")
                st.dataframe(
                    df[["Produkt", "Rekomendowany sklep", "koszt", "potrzeba", "dostępność/okazja", "Priorytet", "Cena (zł)", "Wskazówka", "Decyzja"]],
                    use_container_width=True
                )

                col1, col2 = st.columns(2)
                col1.metric("Wykorzystany budżet", f"{allocated:.2f} zł")
                col2.metric("Pozostało środków", f"{budget - allocated:.2f} zł")

                st.divider()

                st.subheader("🛒 Gotowe listy zakupów z podziałem na sklepy")
                col_lidl, col_auchan = st.columns(2)

                df_kupione = df[df["Decyzja"] == "✅ Kup teraz"]

                with col_lidl:
                    st.markdown("### 🟡🔵 Lidl")
                    lidl_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Lidl"]
                    if not lidl_items.empty:
                        for _, r in lidl_items.iterrows():
                            st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka']})*")
                        st.caption(f"Suma w Lidlu: **{lidl_items['Cena (zł)'].sum():.2f} zł**")
                    else:
                        st.info("Brak rekomendowanych zakupów w Lidlu.")

                with col_auchan:
                    st.markdown("### 🔴🟢 Auchan")
                    auchan_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Auchan"]
                    if not auchan_items.empty:
                        for _, r in auchan_items.iterrows():
                            st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka']})*")
                        st.caption(f"Suma w Auchan: **{auchan_items['Cena (zł)'].sum():.2f} zł**")
                    else:
                        st.info("Brak rekomendowanych zakupów w Auchan.")

                odlozone = df[df["Decyzja"] == "⏳ Odłóż"]
                if not odlozone.empty:
                    with st.expander("⏳ Produkty przekraczające budżet (odłożone)"):
                        for _, r in odlozone.iterrows():
                            st.write(f"- **{r['Produkt']}** ({r['Rekomendowany sklep']}) ~ {r['Cena (zł)']:.2f} zł (Priorytet: {r['Priorytet']})")

            except Exception as e:
                st.error(f"Błąd analizy: {e}")
