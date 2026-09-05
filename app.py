import streamlit as st
import pandas as pd
import json
from google import genai
from google.genai import types

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Inteligentne Zakupy: Lidl vs Auchan", layout="wide")

st.title("🛒 Asystent Promocji: Lidl & Auchan")
st.write("Wpisz produkty, a AI przeszuka aktualne oferty i promocje w gazetkach Lidla oraz Auchan, przeliczy priorytety i rozdzieli listę na sklepy.")

# Skala / wagi w panelu bocznym
st.sidebar.header("⚖️ Skala wagowa kryteriów")
waga_koszt = st.sidebar.number_input("Waga: Koszt / Przystępność", value=0.5, step=0.1)
waga_potrzeba = st.sidebar.number_input("Waga: Potrzeba", value=0.4, step=0.1)
waga_dostepnosc = st.sidebar.number_input("Waga: Okazja / Promocja", value=0.3, step=0.1)

budget = st.number_input("Dostępny budżet łącznie (zł):", min_value=0.0, value=250.0, step=25.0)

raw_input = st.text_area(
    "Twoja lista zakupów:", 
    placeholder="np. masło, mleko, filet z kurczaka, kawa ziarnista, papier toaletowy, proszek do prania, czekolada, pomidory",
    height=100
)

def analyze_promotions_and_assign_shops(items_list):
    client = genai.Client(api_key=API_KEY)
    prompt = f"""
    Jesteś polskim asystentem zakupowym.
    Sprawdź aktualne promocje, gazetki i oferty w sieciach handlowych LIDL Polska oraz AUCHAN Polska dla poniższej listy artykułów:
    {', '.join(items_list)}

    Dla każdego artykułu:
    1. "sklep": wybierz 'Lidl' lub 'Auchan' – wskaż ten sklep, w którym ten produkt jest obecnie w lepszej promocji, ma niższą cenę lub korzystniejszą ofertę. Jeśli oferty są zbliżone, wskaż sklep, w którym typowo dany produkt ma lepszy stosunek ceny do jakości.
    2. "cena_pln": oszacuj realną/promocyjną cenę w PLN w wybranym sklepie.
    3. "ocena_koszt": w skali 1-5 pod kątem przystępności (5 = tani/duża oszczędność, 1 = drogi artykuł).
    4. "ocena_potrzeba": w skali 1-5 pod kątem niezbędności (5 = absolutna podstawa żywieniowa/higieniczna, 1 = luksus/słodycze).
    5. "ocena_okazja": w skali 1-5 pod kątem siły promocji/dostępności (5 = duża obniżka w aktualnej gazetce/końcówka promocji, 1 = cena regularna/brak rabatu).
    6. "uwagi": krótki powód wyboru (np. "Promocja w gazetce Lidla", "Taniej w Auchan").

    Zwróć WYŁĄCZNIE poprawny JSON (tablicę obiektów) bez bloków markdown:
    [
      {{"name": "Masło", "sklep": "Lidl", "cena_pln": 5.99, "ocena_koszt": 4.5, "ocena_potrzeba": 5.0, "ocena_okazja": 4.0, "uwagi": "Promocja -30% w Lidlu"}}
    ]
    """

    # Włączamy wyszukiwarkę internetową Google Search (Grounding)
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    last_error = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"Błąd analizy ofert: {last_error}")

if st.button("🔍 Sprawdź promocje i optymalizuj koszyki"):
    if not raw_input.strip():
        st.warning("Wpisz przynajmniej jeden produkt.")
    else:
        items_raw = [x.strip() for x in raw_input.replace("\n", ",").split(",") if x.strip()]
        
        with st.spinner("AI przeszukuje aktualne promocje w gazetkach Lidla i Auchan..."):
            try:
                data = analyze_promotions_and_assign_shops(items_raw)
                parsed = []

                for entry in data:
                    cena = float(entry.get("cena_pln", 10.0))
                    pkt_k = float(entry.get("ocena_koszt", 3.0))
                    pkt_p = float(entry.get("ocena_potrzeba", 3.0))
                    pkt_o = float(entry.get("ocena_okazja", 2.0))

                    # Obliczenie priorytetu ze skali: (koszt * 0.5) + (potrzeba * 0.4) + (dostępność/okazja * 0.3)
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
                        "Wskazówka promocji": entry.get("uwagi", "")
                    })

                df = pd.DataFrame(parsed)
                df = df.sort_values(by="Priorytet", ascending=False).reset_index(drop=True)

                # Przydział w ramach budżetu
                allocated = 0.0
                status = []
                for _, row in df.iterrows():
                    if allocated + row["Cena (zł)"] <= budget:
                        allocated += row["Cena (zł)"]
                        status.append("✅ Kup teraz")
                    else:
                        status.append("⏳ Odłóż")
                df["Decyzja"] = status

                # 1. Główna tabela zbiorcza
                st.subheader("📋 Matryca priorytetów i rekomendacje")
                st.dataframe(
                    df[["Produkt", "Rekomendowany sklep", "koszt", "potrzeba", "dostępność/okazja", "Priorytet", "Cena (zł)", "Wskazówka promocji", "Decyzja"]],
                    width="stretch"
                )

                col1, col2 = st.columns(2)
                col1.metric("Wykorzystany budżet", f"{allocated:.2f} zł")
                col2.metric("Pozostało środków", f"{budget - allocated:.2f} zł")

                st.divider()

                # 2. Pogrupowane koszyki dla sklepów
                st.subheader("🛒 Gotowe listy zakupów z podziałem na sklepy")
                col_lidl, col_auchan = st.columns(2)

                df_kupione = df[df["Decyzja"] == "✅ Kup teraz"]

                with col_lidl:
                    st.markdown("### 🟡🔵 Lidl")
                    lidl_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Lidl"]
                    if not lidl_items.empty:
                        for _, r in lidl_items.iterrows():
                            st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka promocji']})*")
                        st.caption(f"Suma w Lidlu: **{lidl_items['Cena (zł)'].sum():.2f} zł**")
                    else:
                        st.info("Brak rekomendowanych zakupów w Lidlu.")

                with col_auchan:
                    st.markdown("### 🔴🟢 Auchan")
                    auchan_items = df_kupione[df_kupione["Rekomendowany sklep"] == "Auchan"]
                    if not auchan_items.empty:
                        for _, r in auchan_items.iterrows():
                            st.write(f"- **{r['Produkt']}** ~ {r['Cena (zł)']:.2f} zł *({r['Wskazówka promocji']})*")
                        st.caption(f"Suma w Auchan: **{auchan_items['Cena (zł)'].sum():.2f} zł**")
                    else:
                        st.info("Brak rekomendowanych zakupów w Auchan.")

                # Produkty odłożone na później
                odlozone = df[df["Decyzja"] == "⏳ Odłóż"]
                if not odlozone.empty:
                    with st.expander("⏳ Produkty przekraczające obecny budżet (odłożone)"):
                        for _, r in odlozone.iterrows():
                            st.write(f"- **{r['Produkt']}** ({r['Rekomendowany sklep']}) ~ {r['Cena (zł)']:.2f} zł (Priorytet: {r['Priorytet']})")

            except Exception as e:
                st.error(f"Błąd pobierania danych o promocjach: {e}")
