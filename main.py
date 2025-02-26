import streamlit as st
import pandas as pd
import os
import json
import anthropic
import hashlib

# Page config
st.set_page_config(page_title="Moxie MD-Nurse Matching", layout="wide")

# Custom CSS
st.markdown("""
<style>
    .match-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        border-left: 4px solid #4e7ddd;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .match-reason {
        background-color: #e9f7fe;
        border-radius: 5px;
        padding: 10px;
        margin-top: 5px;
        border-left: 3px solid #3498db;
    }
    .service-badge {
        background-color: #5c88da;
        color: white;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 12px;
        margin-right: 5px;
        display: inline-block;
    }
    .main-header {
        color: #2c3e50;
        text-align: center;
        margin-bottom: 20px;
    }
    .subheader {
        color: #34495e;
        border-bottom: 1px solid #eee;
        padding-bottom: 10px;
    }
    .explanation {
        background-color: #f5f9ff;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .password-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        background-color: white;
        text-align: center;
    }
    .password-header {
        margin-bottom: 20px;
        color: #2c3e50;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state for password
if 'password_correct' not in st.session_state:
    st.session_state['password_correct'] = False

# Simple password screen
if not st.session_state['password_correct']:
    st.markdown("""
    <div class="password-container">
        <h2 class="password-header">Moxie MD-Nurse Matching System</h2>
        <p>Please enter the password to access the system:</p>
    </div>
    """, unsafe_allow_html=True)
    
    password = st.text_input("Password", type="password", key="password_input")
    
    if st.button("Login"):
        # Check password (MoxieAI2025)
        if hashlib.sha256(password.encode()).hexdigest() == "97ae99ac51b1d9a28affe80d1ec94ca5d1d8e67e2767dde23af9df17cb52c9c2":
            st.session_state['password_correct'] = True
            st.experimental_rerun()
        else:
            st.error("Incorrect password. Please try again.")
    
    # Stop execution here if password is incorrect
    st.stop()

# Main application (only runs if password is correct)
st.markdown("<h1 class='main-header'>Moxie MD-Nurse Matching System</h1>", unsafe_allow_html=True)

# Load data
@st.cache_data
def load_data():
    try:
        doctors_df = pd.read_csv('Medical_List.csv')
        nurses_df = pd.read_csv('hubspot_moxie.csv')
        
        # Filter for medical directors
        doctors_df = doctors_df[doctors_df['Lifecycle Stage'] == 'Medical Director Onboarded']
        
        # Filter for nurses (RN or NP)
        nurses_df = nurses_df[nurses_df['Provider License Type'].notna()]
        nurses_with_license = nurses_df[
            nurses_df['Provider License Type'].str.contains('RN|NP', na=False)
        ]
        
        return doctors_df, nurses_with_license
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None

# Function to create a matching prompt
def create_claude_prompt(search_type, search_value, doctors_df, nurses_df):
    if search_type == "md":
        # Find the doctor in the dataframe
        doctor_row = doctors_df[
            doctors_df.apply(
                lambda row: search_value.lower() in f"{row['First Name']} {row['Last Name']}".lower(), 
                axis=1
            )
        ]
        
        if doctor_row.empty:
            return None, "Doctor not found in database."
        
        doctor = doctor_row.iloc[0]
        
        # Create base prompt
        prompt = f"""
        You are an Operations Manager at Moxie tasked with matching medical directors with nurses.
        
        Doctor Information:
        - Name: {doctor['First Name']} {doctor['Last Name']}
        - Email: {doctor['Email']}
        - State: {doctor['Residing State  (Lives In)']}
        - Onboarded: {doctor['Create Date']}
        
        Using the doctor information above, analyze the following nurse candidates and identify the top 3 best matches based on:
        1. Location match (highest priority - same state is ideal)
        2. Experience level compatibility (experienced doctors can mentor newer nurses)
        3. Service offering alignment
        4. Any specific notes or requirements mentioned
        
        For each match, provide:
        1. The nurse's name
        2. Contact information
        3. A detailed explanation of why they're a good match (be specific about shared location, services, experience level)
        4. A match score out of 10
        
        Available Nurses:
        """
        
        # Add nurse candidates
        same_state_nurses = nurses_df[nurses_df['State (MedSpa Premise)'] == doctor['Residing State  (Lives In)']]
        other_nurses = nurses_df[nurses_df['State (MedSpa Premise)'] != doctor['Residing State  (Lives In)']]
        selected_nurses = pd.concat([same_state_nurses.head(10), other_nurses.head(10)])
        
        for _, nurse in selected_nurses.iterrows():
            # Safe extraction of fields
            nurse_name = str(nurse['Ticket Number Counter']) if pd.notna(nurse['Ticket Number Counter']) else "Unknown"
            nurse_email = str(nurse['Bird Eats Bug Email']) if pd.notna(nurse['Bird Eats Bug Email']) else "No email"
            nurse_license = str(nurse['Provider License Type']) if pd.notna(nurse['Provider License Type']) else "Unknown"
            nurse_experience = str(nurse['Experience Level  ']) if pd.notna(nurse['Experience Level  ']) else "Unknown"
            nurse_state = str(nurse['State (MedSpa Premise)']) if pd.notna(nurse['State (MedSpa Premise)']) else "Unknown"
            nurse_services = str(nurse['Services Provided']) if pd.notna(nurse['Services Provided']) else "None specified"
            nurse_notes = str(nurse['Addt\'l Service Notes']) if pd.notna(nurse['Addt\'l Service Notes']) else "None"
            
            # Append to prompt without using f-string for the notes field
            prompt += f"""
            Nurse:
            - Name: {nurse_name}
            - Email: {nurse_email}
            - License Type: {nurse_license}
            - Experience: {nurse_experience}
            - State: {nurse_state}
            - Services: {nurse_services}
            - Notes: """
            prompt += nurse_notes + "\n\n"
        
        # Add response format instructions
        prompt += """
        Format your response as JSON with the following structure:
        {
            "matches": [
                {
                    "name": "Nurse Name",
                    "email": "nurse@email.com",
                    "match_score": 8.5,
                    "reasoning": "Detailed explanation of why this is a good match"
                },
                ...
            ]
        }
        
        Only include the JSON in your response, nothing else.
        """
        
        return prompt, None
    
    elif search_type == "nurse":
        # Find the nurse
        nurse_row = nurses_df[
            nurses_df.apply(
                lambda row: pd.notna(row['Ticket Number Counter']) and search_value.lower() in str(row['Ticket Number Counter']).lower(),
                axis=1
            )
        ]
        
        if nurse_row.empty:
            return None, "Nurse not found in database."
        
        nurse = nurse_row.iloc[0]
        
        # Safe extraction of fields
        nurse_name = str(nurse['Ticket Number Counter']) if pd.notna(nurse['Ticket Number Counter']) else "Unknown"
        nurse_email = str(nurse['Bird Eats Bug Email']) if pd.notna(nurse['Bird Eats Bug Email']) else "No email"
        nurse_license = str(nurse['Provider License Type']) if pd.notna(nurse['Provider License Type']) else "Unknown"
        nurse_experience = str(nurse['Experience Level  ']) if pd.notna(nurse['Experience Level  ']) else "Unknown"
        nurse_state = str(nurse['State (MedSpa Premise)']) if pd.notna(nurse['State (MedSpa Premise)']) else "Unknown"
        nurse_services = str(nurse['Services Provided']) if pd.notna(nurse['Services Provided']) else "None specified"
        nurse_notes = str(nurse['Addt\'l Service Notes']) if pd.notna(nurse['Addt\'l Service Notes']) else "None"
        
        # Create base prompt
        prompt = """
        You are an Operations Manager at Moxie tasked with matching nurses with medical directors.
        
        Nurse Information:
        """
        prompt += f"""
        - Name: {nurse_name}
        - Email: {nurse_email}
        - License Type: {nurse_license}
        - Experience Level: {nurse_experience}
        - State: {nurse_state}
        - Services: {nurse_services}
        - Additional Notes: """
        prompt += nurse_notes + "\n\n"
        
        prompt += """
        Using the nurse information above, analyze the following medical directors and identify the top 3 best matches based on:
        1. Location match (highest priority - same state is ideal)
        2. Experience level compatibility (experienced doctors can mentor newer nurses)
        3. Service offering alignment
        4. Any specific notes or requirements mentioned
        
        For each match, provide:
        1. The doctor's name
        2. Contact information
        3. A detailed explanation of why they're a good match (be specific about shared location, potential service alignment, experience level)
        4. A match score out of 10
        
        Available Medical Directors:
        """
        
        # Add doctor candidates
        if nurse_state != "Unknown":
            same_state_doctors = doctors_df[doctors_df['Residing State  (Lives In)'].str.contains(nurse_state, na=False)]
            other_doctors = doctors_df[~doctors_df['Residing State  (Lives In)'].str.contains(nurse_state, na=False)]
            selected_doctors = pd.concat([same_state_doctors.head(10), other_doctors.head(10)])
        else:
            selected_doctors = doctors_df.head(20)
        
        for _, doctor in selected_doctors.iterrows():
            doctor_info = f"""
            Doctor:
            - Name: {doctor['First Name']} {doctor['Last Name']}
            - Email: {doctor['Email']}
            - State: {doctor['Residing State  (Lives In)']}
            - Onboarded: {doctor['Create Date']}
            
            """
            prompt += doctor_info
        
        # Add response format instructions
        prompt += """
        Format your response as JSON with the following structure:
        {
            "matches": [
                {
                    "name": "Dr. Name",
                    "email": "doctor@email.com",
                    "match_score": 8.5, 
                    "reasoning": "Detailed explanation of why this is a good match"
                },
                ...
            ]
        }
        
        Only include the JSON in your response, nothing else.
        """
        
        return prompt, None
    
    elif search_type == "manual":
        # Manual entry form
        prompt = f"""
        You are an Operations Manager at Moxie tasked with matching medical directors with nurses.
        
        A user has submitted the following information:
        {search_value}
        
        Based on this information, identify if this is a doctor or a nurse, and suggest potential matches from our database.
        
        For each match, provide:
        1. The name of the matched professional
        2. Contact information if available
        3. A detailed explanation of why they're a good match
        4. A match score out of 10
        
        Format your response as JSON with the following structure:
        {{
            "person_type": "doctor" or "nurse",
            "matches": [
                {{
                    "name": "Name",
                    "email": "email@example.com",
                    "match_score": 8.5,
                    "reasoning": "Detailed explanation of why this is a good match"
                }},
                ...
            ]
        }}
        
        Only include the JSON in your response, nothing else.
        """
        
        return prompt, None

# Function to call Claude API
def query_claude(prompt, api_key):
    client = anthropic.Anthropic(api_key=api_key)
    
    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=4000,
            temperature=0.2,
            system="You are a medical staffing expert at Moxie. You help match medical directors with nurses based on their location, experience, services offered, and other relevant factors. You always respond in JSON format as specified in the prompts.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text
    except Exception as e:
        return json.dumps({"error": str(e)})

# Main application content
doctors_df, nurses_df = load_data()

if doctors_df is None or nurses_df is None:
    st.error("Failed to load data. Please check the data files.")
else:
    # Display stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Medical Directors", len(doctors_df))
    with col2:
        st.metric("Nurses (RN/NP)", len(nurses_df))
    with col3:
        st.markdown("**Powered by:** ChatGPT")
    
    # Get Claude API key from environment variable
    claude_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Show API key status
    if claude_api_key:
        st.success("API key is configured and ready to use")
    else:
        st.error("API key is not configured. Please set the ANTHROPIC_API_KEY environment variable")
    
    # Search options
    st.markdown("<h2 class='subheader'>Find Matches</h2>", unsafe_allow_html=True)
    
    search_type = st.radio(
        "Search by:",
        ("Medical Director", "Nurse", "Manual Entry"),
        horizontal=True
    )
    
    # Convert the search type to a simpler format
    search_type_key = {
        "Medical Director": "md",
        "Nurse": "nurse",
        "Manual Entry": "manual"
    }[search_type]
    
    if search_type_key == "md":
        # Get a list of all doctors for the dropdown
        doctor_names = [f"{row['First Name']} {row['Last Name']}" for _, row in doctors_df.iterrows()]
        selected_doctor = st.selectbox("Select Medical Director:", [""] + doctor_names)
        
        if selected_doctor and st.button("Find Matching Nurses"):
            if not claude_api_key:
                st.error("API key is not configured. Please set the ANTHROPIC_API_KEY environment variable.")
            else:
                with st.spinner("Analyzing and finding the best nurse matches..."):
                    prompt, error = create_claude_prompt(search_type_key, selected_doctor, doctors_df, nurses_df)
                    
                    if error:
                        st.error(error)
                    else:
                        # Call Claude API
                        response = query_claude(prompt, claude_api_key)
                        
                        try:
                            matches = json.loads(response)
                            
                            # Display matches
                            st.markdown(f"<h3>Top Matches for {selected_doctor}</h3>", unsafe_allow_html=True)
                            
                            for match in matches.get("matches", []):
                                st.markdown(f"""
                                <div class="match-card">
                                    <h4>{match['name']} <span style="float:right; background-color:#4CAF50; color:white; padding:5px 10px; border-radius:15px;">Match Score: {match['match_score']}/10</span></h4>
                                    <p><strong>Contact:</strong> {match['email']}</p>
                                    <div class="match-reason">
                                        <p><strong>Why this match works:</strong> {match['reasoning']}</p>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        except json.JSONDecodeError:
                            st.error("Error parsing response. Please try again.")
                            st.text(response)
    
    elif search_type_key == "nurse":
        # Get a list of all nurses for the dropdown
        nurse_names = [str(row['Ticket Number Counter']) for _, row in nurses_df.iterrows() if pd.notna(row['Ticket Number Counter'])]
        selected_nurse = st.selectbox("Select Nurse:", [""] + nurse_names)
        
        if selected_nurse and st.button("Find Matching Medical Directors"):
            if not claude_api_key:
                st.error("API key is not configured. Please set the ANTHROPIC_API_KEY environment variable.")
            else:
                with st.spinner("Analyzing and finding the best medical director matches..."):
                    prompt, error = create_claude_prompt(search_type_key, selected_nurse, doctors_df, nurses_df)
                    
                    if error:
                        st.error(error)
                    else:
                        # Call Claude API
                        response = query_claude(prompt, claude_api_key)
                        
                        try:
                            matches = json.loads(response)
                            
                            # Display matches
                            st.markdown(f"<h3>Top Matches for {selected_nurse}</h3>", unsafe_allow_html=True)
                            
                            for match in matches.get("matches", []):
                                st.markdown(f"""
                                <div class="match-card">
                                    <h4>{match['name']} <span style="float:right; background-color:#4CAF50; color:white; padding:5px 10px; border-radius:15px;">Match Score: {match['match_score']}/10</span></h4>
                                    <p><strong>Contact:</strong> {match['email']}</p>
                                    <div class="match-reason">
                                        <p><strong>Why this match works:</strong> {match['reasoning']}</p>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        except json.JSONDecodeError:
                            st.error("Error parsing response. Please try again.")
                            st.text(response)
    
    else:  # Manual entry
        st.markdown("""
        <div class="explanation">
            Enter information about the doctor or nurse you want to match. Include details like:
            <ul>
                <li>Name and role (MD, RN, NP)</li>
                <li>State/location</li>
                <li>Experience level</li>
                <li>Services offered/interested in</li>
                <li>Any special requirements or notes</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        user_input = st.text_area("Enter professional information:", height=150)
        
        if user_input and st.button("Find Matches"):
            if not claude_api_key:
                st.error("API key is not configured. Please set the ANTHROPIC_API_KEY environment variable.")
            else:
                with st.spinner("Analyzing input and finding the best matches..."):
                    prompt, error = create_claude_prompt(search_type_key, user_input, doctors_df, nurses_df)
                    
                    if error:
                        st.error(error)
                    else:
                        # Call Claude API
                        response = query_claude(prompt, claude_api_key)
                        
                        try:
                            matches = json.loads(response)
                            
                            # Display person type
                            person_type = matches.get("person_type", "professional")
                            st.markdown(f"<h3>Top Matches for this {person_type.capitalize()}</h3>", unsafe_allow_html=True)
                            
                            for match in matches.get("matches", []):
                                st.markdown(f"""
                                <div class="match-card">
                                    <h4>{match['name']} <span style="float:right; background-color:#4CAF50; color:white; padding:5px 10px; border-radius:15px;">Match Score: {match['match_score']}/10</span></h4>
                                    <p><strong>Contact:</strong> {match['email']}</p>
                                    <div class="match-reason">
                                        <p><strong>Why this match works:</strong> {match['reasoning']}</p>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        except json.JSONDecodeError:
                            st.error("Error parsing response. Please try again.")
                            st.text(response)
    
    # Explanation of how it works
    with st.expander("How the ChatGPT Matching System Works"):
        st.markdown("""
        This matching system uses ChatGPT, OpenAI's advanced AI assistant, to intelligently match medical directors with nurses based on multiple factors:
        
        1. **Location Matching**: ChatGPT prioritizes professionals in the same state to ensure licensing compatibility.
        
        2. **Experience Level Compatibility**: ChatGPT considers the experience levels of both professionals, often matching experienced doctors with newer nurses who need mentorship.
        
        3. **Service Alignment**: ChatGPT analyzes the services provided by nurses and looks for doctors with relevant expertise.
        
        4. **Notes Analysis**: ChatGPT reviews additional notes for special requirements or preferences that might impact matching.
        
        5. **Match Score**: ChatGPT provides a score out of 10 with detailed reasoning to explain why each match works well.
        
        The system intelligently processes information from your CSV files to find the most compatible professional pairings based on context and details that might not be captured by a simple algorithm.
        """)
