"""Indian States and Agricultural Districts Directory for CropScope farmer registration.
Provides structured suggestions while supporting custom entries.
"""

from __future__ import annotations

INDIAN_STATES_DISTRICTS: dict[str, list[str]] = {
    "Andhra Pradesh": [
        "Anantapur", "Chittoor", "East Godavari", "Guntur", "Krishna", "Kurnool",
        "Prakasam", "Srikakulam", "Visakhapatnam", "Vizianagaram", "West Godavari", "YSR Kadapa",
    ],
    "Assam": [
        "Barpeta", "Cachar", "Darrang", "Dibrugarh", "Goalpara", "Golaghat",
        "Jorhat", "Kamrup", "Nagaon", "Sonitpur", "Tinsukia",
    ],
    "Bihar": [
        "Arrah", "Begusarai", "Bhagalpur", "Darbhanga", "Gaya", "Katihar",
        "Madhubani", "Muzaffarpur", "Nalanda", "Patna", "Purnia", "Rohtas",
        "Samastipur", "Saran", "Vaishali",
    ],
    "Chhattisgarh": [
        "Bilaspur", "Durg", "Janjgir-Champa", "Korba", "Raigarh", "Raipur", "Rajnandgaon",
    ],
    "Delhi": [
        "Central Delhi", "East Delhi", "New Delhi", "North Delhi", "North West Delhi", "South Delhi", "West Delhi",
    ],
    "Gujarat": [
        "Ahmedabad", "Amreli", "Anand", "Banaskantha", "Bharuch", "Bhavnagar",
        "Gandhinagar", "Jamnagar", "Junagadh", "Kheda", "Kutch", "Mehsana",
        "Morbi", "Navsari", "Patan", "Rajkot", "Sabarkantha", "Surat",
        "Surendranagar", "Vadodara", "Valsad",
    ],
    "Haryana": [
        "Ambala", "Bhiwani", "Faridabad", "Fatehabad", "Gurugram", "Hisar",
        "Jhajjar", "Jind", "Kaithal", "Karnal", "Kurukshetra", "Mahendragarh",
        "Palwal", "Panipat", "Rewari", "Rohtak", "Sirsa", "Sonipat", "Yamunanagar",
    ],
    "Himachal Pradesh": [
        "Bilaspur", "Chamba", "Hamirpur", "Kangra", "Kullu", "Mandi", "Shimla", "Sirmaur", "Solan", "Una",
    ],
    "Jammu and Kashmir": [
        "Anantnag", "Baramulla", "Jammu", "Kathua", "Pulwama", "Srinagar", "Udhampur",
    ],
    "Jharkhand": [
        "Bokaro", "Deoghar", "Dhanbad", "Dumka", "Hazaribagh", "Jamshedpur", "Ranchi",
    ],
    "Karnataka": [
        "Bagalkot", "Ballari", "Belagavi", "Bidar", "Chikkamagaluru", "Chitradurga",
        "Davanagere", "Dharwad", "Hassan", "Haveri", "Kalaburagi", "Mandya",
        "Mysuru", "Raichur", "Shivamogga", "Tumakuru", "Udupi", "Vijayapura",
    ],
    "Kerala": [
        "Alappuzha", "Ernakulam", "Idukki", "Kannur", "Kasaragod", "Kollam",
        "Kottayam", "Kozhikode", "Malappuram", "Palakkad", "Thrissur", "Wayanad",
    ],
    "Madhya Pradesh": [
        "Balaghat", "Barwani", "Betul", "Bhind", "Bhopal", "Chhindwara", "Dewas",
        "Dhar", "Guna", "Gwalior", "Hoshangabad", "Indore", "Jabalpur", "Khandwa",
        "Khargone", "Mandsaur", "Morena", "Narsinghpur", "Neemuch", "Raisen",
        "Rajgarh", "Ratlam", "Rewa", "Sagar", "Satna", "Sehore", "Shajapur",
        "Shivpuri", "Ujjain", "Vidisha",
    ],
    "Maharashtra": [
        "Ahmednagar", "Akola", "Amravati", "Aurangabad", "Beed", "Buldhana",
        "Chandrapur", "Dhule", "Jalgaon", "Jalna", "Kolhapur", "Latur", "Nagpur",
        "Nanded", "Nashik", "Osmanabad", "Parbhani", "Pune", "Sangli", "Satara",
        "Solapur", "Wardha", "Yavatmal",
    ],
    "Odisha": [
        "Balasore", "Bargarh", "Bhadrak", "Cuttack", "Ganjam", "Jajpur",
        "Kalahandi", "Kendrapara", "Mayurbhanj", "Puri", "Sambalpur",
    ],
    "Punjab": [
        "Amritsar", "Barnala", "Bathinda", "Faridkot", "Fatehgarh Sahib",
        "Fazilka", "Firozpur", "Gurdaspur", "Hoshiarpur", "Jalandhar",
        "Kapurthala", "Ludhiana", "Mansa", "Moga", "Muktsar", "Pathankot",
        "Patiala", "Rupnagar", "SAS Nagar (Mohali)", "Sangrur", "SBS Nagar", "Tarn Taran",
    ],
    "Rajasthan": [
        "Ajmer", "Alwar", "Banswara", "Baran", "Barmer", "Bharatpur", "Bhilwara",
        "Bikaner", "Chittorgarh", "Churu", "Dausa", "Ganganagar", "Hanumangarh",
        "Jaipur", "Jaisalmer", "Jalore", "Jhalawar", "Jhunjhunu", "Jodhpur",
        "Kota", "Nagaur", "Pali", "Sikar", "Tonk", "Udaipur",
    ],
    "Tamil Nadu": [
        "Ariyalur", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul", "Erode",
        "Kanchipuram", "Karur", "Madurai", "Nagapattinam", "Namakkal", "Perambalur",
        "Pudukkottai", "Ramanathapuram", "Salem", "Sivaganga", "Thanjavur", "Theni",
        "Thoothukudi", "Tiruchirappalli", "Tirunelveli", "Tiruppur", "Vellore", "Villupuram", "Virudhunagar",
    ],
    "Telangana": [
        "Adilabad", "Bhadradri Kothagudem", "Jagtial", "Karimnagar", "Khammam",
        "Mahabubnagar", "Medak", "Nalgonda", "Nizamabad", "Rangareddy",
        "Sangareddy", "Siddipet", "Suryapet", "Warangal",
    ],
    "Uttar Pradesh": [
        "Agra", "Aligarh", "Amroha", "Ayodhya", "Azamgarh", "Bareilly", "Basti",
        "Bijnor", "Budaun", "Bulandshahr", "Deoria", "Etah", "Etawah", "Farrukhabad",
        "Fatehpur", "Firozabad", "Ghaziabad", "Gorakhpur", "Hapur", "Hardoi",
        "Hathras", "Jaunpur", "Jhansi", "Kanpur", "Lakhimpur Kheri", "Lalitpur",
        "Lucknow", "Mainpuri", "Mathura", "Meerut", "Mirzapur", "Moradabad",
        "Muzaffarnagar", "Pilibhit", "Prayagraj", "Raebareli", "Rampur",
        "Saharanpur", "Sambhal", "Shahjahanpur", "Sitapur", "Sonbhadra", "Sultanpur", "Unnao", "Varanasi",
    ],
    "Uttarakhand": [
        "Dehradun", "Haridwar", "Nainital", "Pauri Garhwal", "Udham Singh Nagar",
    ],
    "West Bengal": [
        "Bankura", "Birbhum", "Cooch Behar", "Dakshin Dinajpur", "Darjeeling",
        "Hooghly", "Howrah", "Jalpaiguri", "Malda", "Murshidabad", "Nadia",
        "North 24 Parganas", "Paschim Bardhaman", "Paschim Medinipur",
        "Purba Bardhaman", "Purba Medinipur", "South 24 Parganas", "Uttar Dinajpur",
    ],
}


def get_all_states() -> list[str]:
    """Return sorted list of supported Indian states."""
    return sorted(list(INDIAN_STATES_DISTRICTS.keys()))


def get_districts_for_state(state_name: str) -> list[str]:
    """Return sorted list of districts for a given state."""
    return sorted(INDIAN_STATES_DISTRICTS.get(state_name, []))
