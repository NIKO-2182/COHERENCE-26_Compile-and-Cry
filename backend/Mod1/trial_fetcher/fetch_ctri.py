import requests
from bs4 import BeautifulSoup
import json
import re
from io import BytesIO
from PIL import Image
import os

CTRI_URL = "https://ctri.nic.in/Clinicaltrials/pubview.php"
POST_URL = "https://ctri.nic.in/Clinicaltrials/pubview2.php"

# Reusing known cities mapping from the React component to identify locations
KNOWN_CITIES = {
  "Ahmedabad", "Aurangabad", "Bengaluru", "Bhopal", "Chennai", "Coimbatore",
  "Delhi", "Faridabad", "Gurgaon", "Guwahati", "Hyderabad", "Indore", "Jaipur",
  "Kochi", "Kolkata", "Lucknow", "Ludhiana", "Madurai", "Mangaluru", "Mumbai",
  "Nagpur", "Nashik", "New Delhi", "Noida", "Patna", "Pune", "Raipur", "Ranchi",
  "Surat", "Thiruvananthapuram", "Vadodara", "Varanasi", "Vijayawada", "Visakhapatnam"
}

KNOWN_STATES = {
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
  "Chhattisgarh", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
  "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
  "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
  "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
  "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"
}

def clean_text(text):
    if not text: return ""
    return re.sub(r'\r\n|\r|\n', ' ', text).strip()

def extract_label_value(soup, label_text):
    # CTRI details are typically in tables where the left column is the label and right is the value
    for td in soup.find_all('td'):
        if td.text and label_text.lower() in td.text.lower():
            next_td = td.find_next_sibling('td')
            if next_td: return clean_text(next_td.text)
    return "Unknown"

def parse_trial_page(session, enc_url):
    trial = {
        "nct_id": "", "title": "", "city": "Unknown", "inclusion_criteria": "", "exclusion_criteria": ""
    }
    
    res = session.get(enc_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Try finding CTRI Number for nct_id
    nct_id = extract_label_value(soup, 'CTRI Number')
    if nct_id == "Unknown" or not nct_id:
        match = re.search(r'CTRI/\d+/\d+/\d+', res.text)
        if match: nct_id = match.group(0)
    trial['nct_id'] = nct_id.split('\xa0')[0].replace('\xa0', '').strip()

    # Try finding title
    title1 = extract_label_value(soup, 'Public Title')
    title2 = extract_label_value(soup, 'Scientific Title')
    trial['title'] = title1 if title1 != "Unknown" else title2
    
    # Extract criteria using full text parsing
    text_content = soup.get_text(separator=' ')
    
    # Clean up excess whitespace
    text_content = re.sub(r'\s+', ' ', text_content)
    
    inc_match = re.search(r'Inclusion\s*Criteria(.*?)Exclusion\s*Criteria', text_content, re.I | re.S)
    if inc_match:
        # Check if 'Details' exists to skip the age/gender fields if present
        details_match = re.search(r'Details\s*(.*?)$', inc_match.group(1), re.I | re.S)
        if details_match:
            trial['inclusion_criteria'] = details_match.group(1).strip()
        else:
            trial['inclusion_criteria'] = inc_match.group(1).replace('Modification(s)', '').strip()
            
    exc_match = re.search(r'Exclusion\s*Criteria(.*?)(Method of Generating|Method of Concealment|Date of First Enrollment|Target Sample Size|No of Sites)', text_content, re.I | re.S)
    if exc_match:
        details_match = re.search(r'Details\s*(.*?)$', exc_match.group(1), re.I | re.S)
        if details_match:
            trial['exclusion_criteria'] = details_match.group(1).strip()
        else:
            trial['exclusion_criteria'] = exc_match.group(1).replace('Modification(s)', '').strip()
            
    for city in KNOWN_CITIES:
        if city.lower() in text_content.lower():
            trial['city'] = city
            break
            
    return trial

def main():
    print("Initializing CTRI session...")
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/90.0.0.0 Safari/537.36'
    })
    
    res = session.get(CTRI_URL)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    try:
        csrf = soup.find('input', {'name': 'csrf_token'})['value']
        ncform = soup.find('input', {'name': '__ncforminfo'})['value']
    except TypeError:
        print("Could not find CSRF token. The CTRI site might be temporarily blocking requests or layout changed.")
        return
        
    print("Fetching CAPTCHA...")
    cap_res = session.get('https://ctri.nic.in/Clinicaltrials/captchafiles/captchasecurityimages.php')
    
    try:
        img = Image.open(BytesIO(cap_res.content))
        img.show()
    except Exception as e:
        print("Could not open captcha image automatically. Please make sure Pillow is installed.")
        with open('captcha.jpg', 'wb') as f: f.write(cap_res.content)
        print("CAPTCHA saved as captcha.jpg in the current directory. Please open it manually.")
        
    t3 = input("Enter the 5 characters from the CAPTCHA image: ").strip()
    
    data = {
        'csrf_token': csrf,
        '__ncforminfo': ncform,
        'searchword': 'Type 2 Diabetes',
        'searchtype': '2', # Health Condition / Problem Studied
        'T3': t3
    }
    
    print("\nSubmitting search for 'Type 2 Diabetes' (Health Condition)...")
    res2 = session.post(POST_URL, data=data)
    soup2 = BeautifulSoup(res2.text, 'html.parser')
    
    trials = []
    
    # Find all trial links
    links = soup2.find_all('a', href=re.compile(r'pmaindet2\.php\?EncHid='))
    unique_links = []
    for link in links:
        match = re.search(r"'(pmaindet2\.php\?.*?)'", link['href'])
        if match:
            url = match.group(1).replace('&amp;', '&')
            if url not in unique_links:
                unique_links.append(url)
    
    print(f"Found {len(unique_links)} unique trial URLs on the first page.")
    
    limit = 50 # Limit to 20 for testing due to slow CTRI server (change as needed)
    print(f"Fetching details for the first {limit} trials to generate JSON...")
    
    for i, link in enumerate(unique_links[:limit]):
        full_url = "https://ctri.nic.in/Clinicaltrials/" + link
        print(f"  [{i+1}/{limit}] Fetching {full_url} ...")
        try:
            trial_data = parse_trial_page(session, full_url)
            trials.append(trial_data)
        except Exception as e:
            print(f"  -> Error fetching {link}: {e}")
            
    out_file = 'clinical_trials_diabetes.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(trials, f, indent=2)
        
    print(f"\nDone! Saved {len(trials)} trials to {out_file}.")
    print("You can use this JSON output directly in your React map component by importing it.")

if __name__ == "__main__":
    main()
