import streamlit as st
import pandas as pd
import json
from google import genai

API_KEY = "AQ.Ab8RN6L7UO4NqURBJQJyKPIN9MXXiFKDqxgyn1PTcIqWE3hV5w"

st.set_page_config(page_title="Inteligentna Lista Zakupów AI", layout="centered")

st.title("🛒 Asystent Zakupowy AI")
st.write("Wpisz produkty, a AI oszacuje prawdziwe ceny w Polsce i wyznaczy priorytety.")

budget = st.number_input("Twój budżet (zł):", min_value=0.0, value=500.0, step=50.0)

raw_input = st.text_area(
    "Lista zakupów:", 
    placeholder="np. Perfumy, żel pod prysznic, dywan, laptop, mleko, chleb, jajka, rower",
    height=120
)

def evaluate_items_with_ai(items_list):
    client = genai.Client(api_key=API_KEY)
    prompt = f"""
    Dla podanej listy produktów oszacuj typową, średnią cenę rynkową w Polsce (w PLN), określ kategorię oraz zdecyduj, czy jest to potrzeba podstawowa (jedzenie, podstawowa higiena, zdrowie, karma/weterynarz dla zwierząt domowych, absolutnie niezbędne utrzymanie domu).
    Waga priorytetu to liczba całkowita od 1 do 5 (5 = absolutny niezbędnik do życia, 1 = luksus/zachcianka).

    Lista: {', '.join(items_list)}

    Zwróć WYŁĄCZNIE czysty format JSON (tablica obiektów) bez bloków markdown:
    [
      {{"name": "nazwa", "price": 150.0, "category": "Kategoria", "is_essential": true, "weight": 4}}
    ]
    """

    models_to_try = []
    try:
        for m in client.models.list():
            m_name = getattr(m, 'name', '')
            if 'flash' in m_name:
                models_to_try.append(m_name.replace('models/', ''))
    except Exception:
        pass

    if not models_to_try:
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"Błąd modelu: {last_error}")

if st.button("Analizuj i ułóż plan zakupów"):
    if not raw_input.strip():
        st.warning("Wpisz przynajmniej jeden produkt.")
    else:
        items_raw = [x.strip() for x in raw_input.replace("\n", ",").split(",") if x.strip()]
        
        with st.spinner("AI sprawdza realne ceny i priorytety..."):
            try:
                ai_data = evaluate_items_with_ai(items_raw)
                parsed_items = []
                for entry in ai_data:
                    price = float(entry.get("price", 50.0))
                    weight = int(entry.get("weight", 3))
                    is_essential = entry.get("is_essential", False)
                    score = round((weight * 30) / (price ** 0.25), 2)
                    
                    parsed_items.append({
                        "Przedmiot": entry.get("name", "").capitalize(),
                        "Kategoria": entry.get("category", "Inne"),
                        "Szacowana cena (PLN)": price,
                        "Potrzeba podstawowa": "TAK" if is_essential else "NIE",
                        "Priorytet": score
                    })

                df = pd.DataFrame(parsed_items)
                df = df.sort_values(by="Priorytet", ascending=False).reset_index(drop=True)

                allocated = 0.0
                status = []
                for _, row in df.iterrows():
                    if allocated + row["Szacowana cena (PLN)"] <= budget:
                        allocated += row["Szacowana cena (PLN)"]
                        status.append("✅ Kup teraz")
                    else:
                        status.append("⏳ Odłóż")
                
                df["Decyzja"] = status

                st.subheader("Rekomendacja zakupowa")
                st.dataframe(df[["Przedmiot", "Kategoria", "Szacowana cena (PLN)", "Potrzeba podstawowa", "Decyzja"]], width="stretch")

                col1, col2 = st.columns(2)
                col1.metric("Wykorzystany budżet", f"{allocated:.2f} PLN")
                col2.metric("Pozostało środków", f"{budget - allocated:.2f} PLN")
                
            except Exception as e:
                st.error(f"Błąd analizy: {e}")
