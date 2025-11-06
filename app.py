# app.py
import streamlit as st
import google.generativeai as genai
import requests
import json
import os
from google.cloud import firestore
from datetime import datetime, time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# --- TEMPORARY DEBUGGING START ---
temp_gemini_key = os.getenv("GEMINI_API_KEY")
print(f"DEBUG: GEMINI_API_KEY loaded from .env: {temp_gemini_key}")
if not temp_gemini_key:
    st.error("DEBUG: GEMINI_API_KEY is None! Check your .env file.")
# --- TEMPORARY DEBUGGING END ---


# Configure APIs
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.error("Gemini API Key not found. Please set GEMINI_API_KEY in your .env file.")
# Initialize Firestore
# Ensure you have your service account key file at the path specified in .env
try:
    if os.path.exists(os.getenv("FIRESTORE_CREDENTIALS")):
        db = firestore.Client.from_service_account_json(os.getenv("FIRESTORE_CREDENTIALS"))
    else:
        st.error("Firestore credentials file not found. Please check your .env and file path.")
        db = None # Set db to None if credentials fail
except Exception as e:
    st.error(f"Error initializing Firestore: {e}")
    db = None

# --- Gemini AI Chatbot Function ---
def get_gemini_response(user_input):
    try:
        model = genai.GenerativeModel("gemini-pro")
        chat = model.start_chat(history=[])
        response = chat.send_message(user_input)
        return response.text
    except Exception as e:
        return f"Error communicating with Gemini API: {e}. Please check your API key and network connection."

# --- Firestore Medicine Reminder Functions ---
def add_reminder_to_firestore(user_id, medicine_name, dosage, reminder_time_str):
    if db is None:
        st.error("Firestore is not initialized. Cannot add reminder.")
        return False
    try:
        doc_ref = db.collection("reminders").add({
            "user_id": user_id,
            "medicine_name": medicine_name,
            "dosage": dosage,
            "time": reminder_time_str,
            "created_at": firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        st.error(f"Error adding reminder to Firestore: {e}")
        return False

def get_reminders_from_firestore(user_id):
    if db is None:
        st.error("Firestore is not initialized. Cannot retrieve reminders.")
        return []
    try:
        reminders_ref = db.collection("reminders").where("user_id", "==", user_id).order_by("created_at").stream()
        reminders = []
        for doc in reminders_ref:
            reminders.append(doc.to_dict())
        return reminders
    except Exception as e:
        st.error(f"Error fetching reminders from Firestore: {e}")
        return []

# --- Google Maps Places API Function ---
def find_nearby_clinics(location):
    if not GOOGLE_MAPS_API_KEY:
        st.error("Google Maps API Key is not set. Please add it to your .env file.")
        return []

    base_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": f"clinics or hospitals near {location}",
        "key": GOOGLE_MAPS_API_KEY
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()
        
        clinics = []
        if data.get("results"):
            for place in data["results"][:5]: # Limit to 5 results
                name = place.get("name")
                address = place.get("formatted_address")
                rating = place.get("rating", "N/A")
                place_id = place.get("place_id")
                
                if name and address and place_id:
                    google_maps_link = f"https://www.google.com/maps/search/?api=1&query={name},{address}&query_place_id={place_id}"
                    clinics.append({
                        "name": name,
                        "address": address,
                        "rating": rating,
                        "link": google_maps_link
                    })
        return clinics
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to Google Maps API: {e}. Check your API key and network.")
        return []
    except json.JSONDecodeError:
        st.error("Error decoding JSON response from Google Maps API.")
        return []

# --- Streamlit UI ---
st.set_page_config(
    page_title="MediAssist",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("MediAssist – AI Health Companion for Rural Patients")

# Custom CSS for a cleaner UI
st.markdown("""
    <style>
    .stApp {
        background-color: #f0f2f6;
    }
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.1em;
        font-weight: bold;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 20px;
        font-size: 16px;
        cursor: pointer;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: #e0e0e0;
        color: #333;
        text-align: center;
        padding: 10px;
        font-size: 0.9em;
        border-top: 1px solid #ccc;
    }
    </style>
    """, unsafe_allow_html=True)

# Generate a simple unique user ID for this session (for medicine reminders)
# In a real app, you'd have proper user authentication
if "user_id" not in st.session_state:
    st.session_state.user_id = "user_" + str(datetime.now().timestamp()).replace(".", "")

tab1, tab2, tab3 = st.tabs(["🩺 AI Health Chat", "💊 Medicine Reminders", "🏥 Find Clinics"])

with tab1:
    st.header("AI Health Chat")
    st.write("Describe your symptoms, and I'll provide some general guidance.")

    user_symptom_input = st.text_area("Tell me your symptoms (e.g., 'I have fever and headache.' or 'मुझे बुखार और सर दर्द है।')", height=100)

    if st.button("Get Health Advice"):
        if user_symptom_input:
            with st.spinner("Analyzing symptoms..."):
                response = get_gemini_response(user_symptom_input)
                st.info(response)
        else:
            st.warning("Please enter your symptoms to get advice.")

with tab2:
    st.header("Medicine Reminders")
    st.write("Set reminders for your medications.")

    with st.form("medicine_reminder_form", clear_on_submit=True):
        medicine_name = st.text_input("Medicine Name", key="med_name_input")
        dosage = st.text_input("Dosage (e.g., '1 tablet', '5ml')", key="dosage_input")
        
        # Default to current time for convenience
        current_time = datetime.now().time()
        reminder_time = st.time_input("Reminder Time", value=current_time, key="time_input")

        submit_reminder = st.form_submit_button("Add Reminder")

        if submit_reminder:
            if medicine_name and dosage and reminder_time:
                # Format time as HH:MM string for storage
                reminder_time_str = reminder_time.strftime("%H:%M")
                if add_reminder_to_firestore(st.session_state.user_id, medicine_name, dosage, reminder_time_str):
                    st.success(f"Reminder for {medicine_name} at {reminder_time_str} added!")
                else:
                    st.error("Failed to add reminder.")
            else:
                st.warning("Please fill in all fields for the reminder.")

    st.subheader("Your Saved Reminders")
    user_reminders = get_reminders_from_firestore(st.session_state.user_id)
    if user_reminders:
        # Sort reminders by time for better readability
        sorted_reminders = sorted(user_reminders, key=lambda x: datetime.strptime(x["time"], "%H:%M").time())
        
        # Create a list of dictionaries for tabular display
        display_data = []
        for reminder in sorted_reminders:
            display_data.append({
                "Medicine": reminder["medicine_name"],
                "Dosage": reminder["dosage"],
                "Time": reminder["time"]
            })
        st.table(display_data)
    else:
        st.info("No medicine reminders set yet. Add one above!")

with tab3:
    st.header("Find Clinics")
    st.write("Search for nearby clinics or hospitals.")

    location_input = st.text_input("Enter city or pin code (e.g., 'Lucknow', '226001')", key="location_input")

    if st.button("Search Clinics"):
        if location_input:
            with st.spinner("Searching for clinics..."):
                clinics = find_nearby_clinics(location_input)
                if clinics:
                    for i, clinic in enumerate(clinics):
                        st.markdown(f"**{i+1}. {clinic['name']}** – {clinic['address']}<br>"
                                    f"⭐ {clinic['rating']} | [View on Google Maps]({clinic['link']})",
                                    unsafe_allow_html=True)
                        st.markdown("---")
                else:
                    st.info("No clinics found for your search. Try a different location or check your API key.")
        else:
            st.warning("Please enter a city or pin code to search for clinics.")

# Footer
st.markdown("""
    <div class="footer">
        Built for GenAI Hackathon – Lucknow 2025
    </div>
    """, unsafe_allow_html=True)