import requests
from tkinter import messagebox

def get_currency_rate(currency_code):
    try:
        response = requests.get(f'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode={currency_code}&json')
        data = response.json()
        rate = data[0]['rate']
        return rate
    except Exception as e:
        messagebox.showerror("Error", f"Could not fetch currency rate: {e}")
        return None

def convert_currency(amount, from_currency, to_currency):
    from_rate = get_currency_rate(from_currency)
    to_rate = get_currency_rate(to_currency)
    if from_rate and to_rate:
        return amount * (to_rate / from_rate)
    return None